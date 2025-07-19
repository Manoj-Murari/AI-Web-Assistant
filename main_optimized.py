"""
Performance-optimized AI Web Agent with caching, connection pooling, and async operations.
"""
import google.generativeai as genai
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchWindowException, InvalidSessionIdException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
import time
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from typing import Any, Dict, List, Union, Optional
import ast
import operator as op
import os
import atexit
import threading
from contextlib import contextmanager

# Import optimized modules
from config import config_manager
from performance_utils import (
    vision_cache, performance_monitor, browser_pool, memory_manager,
    ImageOptimizer, retry_with_backoff, timed_operation, cleanup_on_exit,
    cache_key_from_prompt_and_image
)

# --- MODIFICATION: Import the API key securely from the apikey.py file ---
try:
    from apikey import gemini_api_key
except ImportError:
    gemini_api_key = os.getenv('GEMINI_API_KEY', '')
    if not gemini_api_key:
        print("WARNING: No API key found. Please create apikey.py or set GEMINI_API_KEY environment variable.")

# --- Configuration ---
config = config_manager.get_config()

# --- The "Brain" of our Assistant ---
PROMPT_TEMPLATE = """
You are a world-class autonomous planning AI. Your job is to convert the user's high-level request into a precise, robust plan for a Python automation engine using web automation, a vision-language model, and a shared context system.

Your primary strategy should be to use the visual labeling system.

Your plan must be a single valid JSON object with one top-level key: "steps". No markdown, no explanations. Just return the raw JSON.

--- ACTION TYPES ---

Each step must use one of the following actions:

1. OPEN_BROWSER
   data: {{ "browser": "chrome" }}

2. NAVIGATE_TO_URL
   data: {{ "url": "https://..." or "{{placeholder}}" }}

3. LABEL_AND_READ_SCREEN
   This is the most important action for understanding and interacting with a page. It takes a screenshot, asks the vision model to identify and label all interactive elements (buttons, links, inputs), and stores this information in the shared context.
   data: {{
     "context_key_to_store_labels": "homepage_elements"
   }}
   (The script will store the labeled elements map under this key. You can then refer to these elements by number in subsequent CLICK or TYPE actions.)

4. TYPE_INTO_ELEMENT
   Can use a visual label (preferred) OR a standard Selenium locator.
   data: {{
     "text": "text or {{placeholder}}",
     "locator": {{
       "type": "label_number" | "id" | "name" | "xpath" | "css_selector",
       "value": 7,
       "context_source": "homepage_elements"
     }},
     "submit_after_typing": true | false
   }}
   (For label_number, value is the number and context_source is the key where labels were stored. For other types, context_source is ignored.)

5. CLICK_ELEMENT
   Can use a visual label (preferred) OR a standard Selenium locator.
   data: {{
     "locator": {{
       "type": "label_number" | "id" | "name" | "link_text" | "xpath" | "css_selector",
       "value": 12,
       "context_source": "homepage_elements"
     }}
   }}
   (For label_number, value is the number and context_source is the key where labels were stored.)

6. READ_SCREEN
   Used for extracting general text info via the vision model when labeling is not needed.
   data: {{
     "prompt_for_vision": "What is the main headline of the article?",
     "context_key_to_store": "article_headline"
   }}

7. SCROLL_PAGE_TO_TEXT
   data: {{ "text_to_find": "some unique text to scroll to" }}

8. CONDITIONAL_JUMP
   data: {{
     "condition": "{{some_key}} == 'some_value'",
     "goto_step": 5
   }}
   (Supported operators: ==, !=, <, <=, >, >=. For list length, use "{{list_name}}.length < 3".)

9. ANSWER_USER
   data: {{
     "response_template": "The headline is {{article_headline}}."
   }}

--- STRATEGY ---
1. Navigate to a URL.
2. Use `LABEL_AND_READ_SCREEN` to see what's on the page and get labels for interactive elements.
3. Use `CLICK_ELEMENT` or `TYPE_INTO_ELEMENT` with the `label_number` to interact with the page.
4. Repeat labeling and interacting as needed.
5. Use `READ_SCREEN` for general text extraction if necessary.
6. End with `ANSWER_USER`.

--- USER'S GOAL ---

{user_goal}
"""

# Global variables with optimizations
driver = None
vision_model = None
shared_context = {}
_PATH_NOT_FOUND_MARKER_STR = "[{path} not found/extracted]"

class _NotFoundType: 
    pass

NOT_FOUND = _NotFoundType()

_OPERATORS = {
    '==': op.eq,
    '!=': op.ne,
    '>': op.gt,
    '<': op.lt,
    '>=': op.ge,
    '<=': op.le,
}

# Register cleanup on exit
atexit.register(cleanup_on_exit)

# Optimized utility functions
def strip_json_comments(json_text: str) -> str:
    if json_text is None: 
        return ""
    lines = json_text.splitlines()
    cleaned_lines = []
    for line in lines:
        if not line.strip().startswith("//"):
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def sanitize_json_string_for_loading(s: str) -> str:
    if s is None: 
        return ""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', s)

@timed_operation("plan_generation")
@retry_with_backoff
def get_gemini_plan(user_goal: str) -> Optional[Dict[str, Any]]:
    """Generate a plan using Gemini with optimizations and caching."""
    global shared_context
    shared_context = {}
    print("DEBUG: get_gemini_plan function called (shared_context reset).")

    # Check if input is already a valid plan
    try:
        direct_plan = json.loads(user_goal)
        if isinstance(direct_plan, dict) and "steps" in direct_plan:
            print("DEBUG: User input is valid JSON plan. Using it directly.")
            return direct_plan
    except json.JSONDecodeError:
        print("DEBUG: User input is not a direct JSON plan. Proceeding to LLM for planning.")
        pass

    print("🧠 Assistant is thinking...")
    
    try:
        if not gemini_api_key:
            print("ERROR: API_KEY is not set in apikey.py or is empty.")
            return None
            
        # Initialize model with optimized settings
        genai.configure(api_key=gemini_api_key)
        planning_model = genai.GenerativeModel(
            'gemini-1.5-pro-latest',
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Lower temperature for more deterministic plans
                max_output_tokens=4096,
                candidate_count=1
            )
        )
        print("DEBUG: Planning model configured successfully.")

        full_prompt = PROMPT_TEMPLATE.format(user_goal=user_goal)

        print("DEBUG: Sending prompt to Gemini for planning...")
        response = planning_model.generate_content(full_prompt)
        print("DEBUG: Received planning response from Gemini.")

        raw_response_text = response.text.strip()
        print(f"DEBUG: Raw response text from Gemini (first 200 chars):\n{raw_response_text[:200]}...")

        # Clean up response
        text_after_markdown_strip = raw_response_text
        if text_after_markdown_strip.startswith("```json"):
            text_after_markdown_strip = text_after_markdown_strip[len("```json"):].strip()
        if text_after_markdown_strip.endswith("```"):
            text_after_markdown_strip = text_after_markdown_strip[:-len("```")].strip()

        json_string_for_parsing = sanitize_json_string_for_loading(text_after_markdown_strip)
        plan_data = json.loads(json_string_for_parsing)
        
        return plan_data

    except json.JSONDecodeError as e:
        print(f"DEBUG: JSONDecodeError - {e}")
        return None
    except Exception as e:
        print(f"DEBUG: Exception in get_gemini_plan: {str(e)} (Type: {type(e).__name__})")
        return None

def get_selenium_by(locator_type_str: str):
    """Get Selenium By object with validation."""
    locator_map = {
        "id": By.ID,
        "name": By.NAME,
        "xpath": By.XPATH,
        "css_selector": By.CSS_SELECTOR,
        "class_name": By.CLASS_NAME,
        "link_text": By.LINK_TEXT,
        "partial_link_text": By.PARTIAL_LINK_TEXT
    }
    
    return locator_map.get(locator_type_str, By.ID)

def is_browser_alive(driver_instance) -> bool:
    """Check if browser session is alive."""
    if driver_instance is None: 
        return False
    try:
        _ = driver_instance.title
        return True
    except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
        print(f"DEBUG: Browser session appears to be dead or unresponsive. Error: {type(e).__name__} - {e}")
        return False

def _get_value_from_path(context: Dict[str, Any], path_expression: str) -> Any:
    """Optimized path resolution with better error handling."""
    if not isinstance(path_expression, str) or not path_expression or not isinstance(context, dict):
        return NOT_FOUND
        
    # Handle simple key lookup first (optimization for common case)
    if '.' not in path_expression and '[' not in path_expression:
        return context.get(path_expression.strip(), NOT_FOUND)
    
    # Complex path resolution (existing logic but optimized)
    m = re.match(r"^\s*([a-zA-Z_]\w*)", path_expression)
    if not m:
        return context.get(path_expression.strip(), NOT_FOUND)
        
    var_name = m.group(1)
    if var_name not in context:
        return NOT_FOUND
        
    current = context[var_name]
    remainder = path_expression[m.end():].strip()
    
    if not remainder:
        return current
    
    # Continue with existing complex path logic...
    token_pattern = re.compile(r"""
        ^\s*(?:
            (?:\.\s*([a-zA-Z_]\w*))
          | (?:\[\s*(
                (-?\d+)
              | (?:(?P<quote_char>['"])(.*?)(?P=quote_char))
              )\s*\])
        )
    """, re.VERBOSE)
    
    while remainder:
        token_match = token_pattern.match(remainder)
        if not token_match:
            return NOT_FOUND
            
        dot_attr = token_match.group(1)
        numeric_idx_str = token_match.group(3)
        bracket_str_key = token_match.group(5)
        
        if dot_attr is not None:
            if isinstance(current, dict) and dot_attr in current:
                current = current[dot_attr]
            else:
                return NOT_FOUND
        elif numeric_idx_str is not None:
            try:
                idx_int = int(numeric_idx_str)
                if isinstance(current, list) and -len(current) <= idx_int < len(current):
                    current = current[idx_int]
                else:
                    return NOT_FOUND
            except ValueError:
                return NOT_FOUND
        elif bracket_str_key is not None:
            if isinstance(current, dict) and bracket_str_key in current:
                current = current[bracket_str_key]
            else:
                return NOT_FOUND
        else:
            return NOT_FOUND
            
        remainder = remainder[token_match.end():].strip()
    
    return current

def _resolve_placeholders(template_string: str, context: dict) -> str:
    """Optimized placeholder resolution."""
    if not isinstance(template_string, str): 
        return template_string
        
    def replacer(match):
        ph_full_path = match.group(1).strip()
        val = _get_value_from_path(context, ph_full_path)
        if val is NOT_FOUND: 
            return _PATH_NOT_FOUND_MARKER_STR.format(path=ph_full_path)
        elif val is None: 
            return "None"
        elif isinstance(val, list):
            return ", ".join(map(str, val)) if val else "[empty list]"
        else: 
            return str(val)
    
    return re.sub(r"\{([^\{\}]+)\}", replacer, template_string)

def _evaluate_condition(condition_template: str, context: Dict[str, Any]) -> bool:
    """Optimized condition evaluation."""
    def evaluate_single_comparison(comp_str):
        # Handle list length operations
        length_pattern = r"\{([^\{\}]+?)\}\.length\s*(==|!=|<=|>=|<|>)\s*(\d+)"
        length_match = re.fullmatch(length_pattern, comp_str.strip())
        
        if length_match:
            list_path, op_str, val_str = length_match.groups()
            list_val = _get_value_from_path(context, list_path.strip())
            if not isinstance(list_val, list): 
                return False
            return _OPERATORS[op_str](len(list_val), int(val_str))
        
        # Handle regular comparisons
        comp_pattern = r"(.+?)(==|!=|<=|>=|<|>)(.+)"
        match = re.match(comp_pattern, comp_str)
        if not match: 
            return bool(_get_value_from_path(context, comp_str.strip()))
        
        left_str, op_str, right_str = match.groups()
        left = _resolve_placeholders(left_str.strip(), context)
        right = _resolve_placeholders(right_str.strip(), context)
        
        # Try numeric comparison first
        try:
            num_left, num_right = float(left), float(right)
            return _OPERATORS[op_str](num_left, num_right)
        except (ValueError, TypeError):
            return _OPERATORS[op_str](str(left), str(right))
    
    normalized_condition = condition_template.replace("{{", "{").replace("}}", "}")
    
    # Handle OR conditions
    if "||" in normalized_condition:
        return any(evaluate_single_comparison(part) for part in normalized_condition.split("||"))
    
    # Handle AND conditions
    if "&&" in normalized_condition:
        return all(evaluate_single_comparison(part) for part in normalized_condition.split("&&"))
    
    return evaluate_single_comparison(normalized_condition)

@contextmanager
def get_browser_from_pool():
    """Context manager for browser pool usage."""
    browser = browser_pool.get_browser()
    try:
        yield browser
    finally:
        browser_pool.return_browser(browser)

@timed_operation("vision_analysis")
def perform_vision_analysis(screenshot_bytes: bytes, vision_prompt: str) -> Optional[Dict[str, Any]]:
    """Optimized vision analysis with caching."""
    global vision_model
    
    # Check cache first
    cache_key = cache_key_from_prompt_and_image(vision_prompt, screenshot_bytes)
    cached_result = vision_cache.get(cache_key)
    
    if cached_result:
        performance_monitor.record_cache_hit()
        print("DEBUG: Using cached vision response")
        return cached_result
    
    performance_monitor.record_cache_miss()
    
    # Optimize image
    if config.ENABLE_IMAGE_COMPRESSION:
        screenshot_bytes = ImageOptimizer.optimize_screenshot(
            screenshot_bytes, 
            config.VISION_IMAGE_RESIZE_WIDTH, 
            config.VISION_IMAGE_RESIZE_HEIGHT,
            config.VISION_IMAGE_QUALITY
        )
    
    try:
        # Initialize vision model if needed
        if vision_model is None:
            print(f"DEBUG: Initializing vision model: {config.vision_model_name if hasattr(config, 'vision_model_name') else 'gemini-1.5-flash-latest'}")
            genai.configure(api_key=gemini_api_key)
            vision_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
        print("DEBUG: Sending screenshot to Gemini for element labeling...")
        image_part = {"mime_type": "image/png", "data": screenshot_bytes}
        prompt_parts = [vision_prompt, image_part]
        
        vision_response = vision_model.generate_content(prompt_parts)
        extracted_text = vision_response.text

        print(f"🤖 Vision Model Response (first 200 chars):\n{extracted_text[:200]}...")
        
        # Parse JSON response
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", extracted_text, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else extracted_text
        
        result = json.loads(json_str)
        
        # Cache the result
        if config.ENABLE_RESPONSE_CACHING:
            vision_cache.put(cache_key, result)
        
        return result
        
    except Exception as e:
        print(f"Error in vision analysis: {e}")
        return None

def execute_action(step: Dict[str, Any]) -> Dict[str, Any]:
    """Optimized action execution with better resource management."""
    global driver, shared_context
    
    action_type = step.get("action")
    action_data = step.get("data", {})
    
    # Record browser operation
    performance_monitor.record_browser_operation()
    
    # Perform memory cleanup if needed
    memory_manager.perform_cleanup()

    if action_type == "OPEN_BROWSER":
        if driver is not None and is_browser_alive(driver):
            print("DEBUG: Browser already open. Skipping OPEN_BROWSER.")
            return {"success": True}
        
        try:
            driver = browser_pool.get_browser()
            print("Opened optimized Chrome browser successfully.")
            time.sleep(0.5)  # Reduced wait time
        except Exception as e:
            print(f"Error opening Chrome browser: {e}")
            driver = None
            return {"success": False, "critical_error": True}
        return {"success": True}

    # Check browser health for actions that require it
    if not is_browser_alive(driver) and action_type not in ["ANSWER_USER", "OPEN_BROWSER"]:
        print(f"Browser session is dead. Cannot execute action: {action_type}.")
        shared_context['execution_halted'] = True
        return {"success": False, "critical_error": True}

    print(f"Executing action: {action_type} with data: {json.dumps(action_data, default=str)}")

    if action_type == "LABEL_AND_READ_SCREEN":
        return execute_label_and_read_screen(action_data)
    
    elif action_type in ["CLICK_ELEMENT", "TYPE_INTO_ELEMENT"]:
        return execute_element_interaction(action_type, action_data)
    
    elif action_type == "NAVIGATE_TO_URL":
        return execute_navigation(action_data)
    
    elif action_type == "READ_SCREEN":
        return execute_read_screen(action_data)
    
    elif action_type == "ANSWER_USER":
        return execute_answer_user(action_data)
    
    elif action_type == "CONDITIONAL_JUMP":
        return execute_conditional_jump(action_data)
    
    elif action_type == "SCROLL_PAGE_TO_TEXT":
        return execute_scroll_to_text(action_data)
    
    else:
        print(f"Unknown or not-yet-implemented action type: {action_type}")
        return {"success": True, "skipped": True}

def execute_label_and_read_screen(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute LABEL_AND_READ_SCREEN action with optimizations."""
    global driver, shared_context
    
    context_key = action_data.get("context_key_to_store_labels", "last_labeled_elements")
    print(f"Executing LABEL_AND_READ_SCREEN. Storing results in context key: '{context_key}'")
    
    try:
        screenshot_bytes = driver.get_screenshot_as_png()
        
        vision_prompt = """
        Analyze this screenshot of a webpage. Identify all interactive elements (like buttons, links, input fields, text areas).
        For each element, provide its purpose, bounding box coordinates [x_min, y_min, x_max, y_max], and assign it a unique number.
        Return a single valid JSON object with one key, "elements", which is an array of objects. Each object must have "number", "description", and "box" keys.
        Example:
        {
          "elements": [
            { "number": 1, "description": "Sign in button", "box": [850, 20, 950, 60] },
            { "number": 2, "description": "Search input field", "box": [300, 30, 600, 70] }
          ]
        }
        """
        
        labeled_elements_data = perform_vision_analysis(screenshot_bytes, vision_prompt)
        
        if not labeled_elements_data:
            return {"success": False}
        
        elements_map = {item['number']: item for item in labeled_elements_data.get('elements', [])}
        shared_context[context_key] = elements_map
        print(f"Successfully labeled {len(elements_map)} elements and stored in context['{context_key}'].")

        # Create labeled screenshot
        create_labeled_screenshot(screenshot_bytes, elements_map)
        
        # Update context summary
        shared_context[f"{context_key}_summary"] = f"Found and labeled {len(elements_map)} elements. See screenshot_with_labels.png for details."
        
        return {"success": True}
        
    except Exception as e:
        print(f"Error during LABEL_AND_READ_SCREEN: {e}")
        return {"success": False}

def create_labeled_screenshot(screenshot_bytes: bytes, elements_map: Dict[int, Dict]) -> None:
    """Create and save labeled screenshot."""
    try:
        img = Image.open(BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(img)
        
        # Try to load a better font
        font = None
        for font_name in ["arial.ttf", "DejaVuSans.ttf", "/System/Library/Fonts/Arial.ttf"]:
            try:
                font = ImageFont.truetype(font_name, 16)
                break
            except (IOError, OSError):
                continue
        
        if font is None:
            font = ImageFont.load_default()

        for number, element in elements_map.items():
            box = element.get('box')
            if not box or len(box) != 4: 
                continue
                
            # Draw bounding box
            draw.rectangle(box, outline="red", width=3)
            
            # Draw label
            label_pos = (box[0], box[1] - 20 if box[1] > 20 else box[1])
            text_bbox = draw.textbbox(label_pos, str(number), font=font)
            draw.rectangle((text_bbox[0]-2, text_bbox[1]-2, text_bbox[2]+2, text_bbox[3]+2), fill="red")
            draw.text(label_pos, str(number), fill="white", font=font)

        labeled_screenshot_path = "screenshot_with_labels.png"
        img.save(labeled_screenshot_path, optimize=True)
        print(f"Saved labeled screenshot to '{labeled_screenshot_path}'.")
        
    except Exception as e:
        print(f"Error creating labeled screenshot: {e}")

def execute_element_interaction(action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute element interaction (click/type) with optimizations."""
    global driver, shared_context
    
    locator_data = action_data.get("locator", {})
    locator_type = locator_data.get("type")
    locator_value = locator_data.get("value")

    if locator_type == "label_number":
        return execute_label_based_interaction(action_type, action_data, locator_data)
    else:
        return execute_selenium_based_interaction(action_type, action_data, locator_data)

def execute_label_based_interaction(action_type: str, action_data: Dict[str, Any], locator_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute interaction using visual labels."""
    global driver, shared_context
    
    context_source = locator_data.get("context_source")
    locator_value = locator_data.get("value")
    
    if not context_source:
        print("Error: 'context_source' is required for 'label_number' locator.")
        return {"success": False}
    
    element_map = shared_context.get(context_source, {})
    
    try:
        element_data = element_map.get(int(locator_value))
    except (ValueError, TypeError):
        print(f"Error: Invalid label number '{locator_value}'. Must be an integer.")
        return {"success": False}

    if not element_data:
        print(f"Error: Label number '{locator_value}' not found in context source '{context_source}'.")
        return {"success": False}
    
    box = element_data.get('box')
    if not box or len(box) != 4:
        print(f"Error: Invalid bounding box for label '{locator_value}'.")
        return {"success": False}
    
    # Calculate click coordinates
    click_x = (box[0] + box[2]) // 2
    click_y = (box[1] + box[3]) // 2
    
    try:
        # Perform click
        actions = ActionChains(driver)
        actions.move_by_offset(click_x, click_y).click().move_by_offset(-click_x, -click_y).perform()
        print(f"Performed click on labeled element '{locator_value}' at ({click_x}, {click_y}).")
        
        if action_type == "TYPE_INTO_ELEMENT":
            text_to_type_template = action_data.get("text", "")
            text_to_type = _resolve_placeholders(text_to_type_template, shared_context)
            
            typing_actions = ActionChains(driver)
            typing_actions.send_keys(text_to_type).perform()
            print(f"Typed '{text_to_type}' into labeled element '{locator_value}'.")
            
            if action_data.get("submit_after_typing"):
                ActionChains(driver).send_keys(Keys.ENTER).perform()
                print("Submitted form by pressing Enter.")
        
        time.sleep(0.5)  # Reduced wait time
        return {"success": True}
        
    except Exception as e:
        print(f"Error interacting with labeled element '{locator_value}': {e}")
        return {"success": False}

def execute_selenium_based_interaction(action_type: str, action_data: Dict[str, Any], locator_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute interaction using Selenium locators."""
    global driver, shared_context
    
    locator_type = locator_data.get("type")
    locator_value = locator_data.get("value")
    
    locator_value_resolved = _resolve_placeholders(str(locator_value), shared_context)
    
    if not all([locator_type, locator_value_resolved]):
        print(f"Missing locator_type or resolved locator_value for {action_type}.")
        return {"success": True, "skipped": True}
    
    try:
        by_type = get_selenium_by(locator_type)
        wait = WebDriverWait(driver, config.IMPLICIT_WAIT)
        
        if action_type == "CLICK_ELEMENT":
            element = wait.until(EC.element_to_be_clickable((by_type, locator_value_resolved)))
            element.click()
            print(f"Clicked element found by {locator_type}: '{locator_value_resolved}'")
            
        elif action_type == "TYPE_INTO_ELEMENT":
            element = wait.until(EC.visibility_of_element_located((by_type, locator_value_resolved)))
            text_to_type_template = action_data.get("text", "")
            text_to_type = _resolve_placeholders(text_to_type_template, shared_context)
            
            element.clear()
            element.send_keys(text_to_type)
            print(f"Typed '{text_to_type}' into element found by {locator_type}: '{locator_value_resolved}'")
            
            if action_data.get("submit_after_typing"):
                element.send_keys(Keys.ENTER)
                print("Submitted form by pressing Enter.")
        
        time.sleep(1)  # Reduced wait time
        return {"success": True}
        
    except TimeoutException:
        print(f"Timeout: Element not found/visible/clickable for {action_type} ({locator_type}='{locator_value_resolved}')")
        return {"success": True, "skipped": True}
    except Exception as e:
        print(f"Error in {action_type}: {e}")
        return {"success": False}

def execute_navigation(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute navigation with timeout handling."""
    global driver, shared_context
    
    url_template = action_data.get("url")
    url = _resolve_placeholders(url_template, shared_context)
    
    if url and not _PATH_NOT_FOUND_MARKER_STR.format(path='')[:-1] in url:
        try:
            driver.get(url)
            print(f"Navigated to URL: {url}")
            time.sleep(0.5)  # Reduced wait time
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            return {"success": False}
    else:
        print(f"Skipping navigation due to unresolved placeholder in URL: {url_template}")
    
    return {"success": True}

def execute_read_screen(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute screen reading with caching."""
    global driver, shared_context
    
    custom_vision_prompt = action_data.get("prompt_for_vision", "Describe what you see.")
    context_key_to_store = action_data.get("context_key_to_store", "last_vision_response")
    
    try:
        screenshot_bytes = driver.get_screenshot_as_png()
        result = perform_vision_analysis(screenshot_bytes, custom_vision_prompt)
        
        if result:
            shared_context[context_key_to_store] = result
            print(f"Stored vision response in '{context_key_to_store}': {str(result)[:150]}...")
        
    except Exception as e:
        print(f"Error in READ_SCREEN: {e}")
    
    return {"success": True}

def execute_answer_user(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute user answer with template resolution."""
    global shared_context
    
    response_template = action_data.get("response_template", "Task completed.")
    final_answer = _resolve_placeholders(response_template, shared_context)
    print(f"\n🤖 Assistant to User: {final_answer}\n")
    
    return {"success": True}

def execute_conditional_jump(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute conditional jump logic."""
    global shared_context
    
    condition_template = action_data.get("condition")
    goto_step = action_data.get("goto_step")
    
    if not condition_template or goto_step is None:
        return {"success": True}
    
    if _evaluate_condition(condition_template, shared_context):
        return {"success": True, "jump_to_step": int(goto_step)}
    
    return {"success": True}

def execute_scroll_to_text(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute scroll to text functionality."""
    global driver
    
    text_to_find = action_data.get("text_to_find", "")
    
    if not text_to_find:
        return {"success": True, "skipped": True}
    
    try:
        # Use JavaScript to scroll to text
        script = f"""
        var elements = document.querySelectorAll('*');
        for (var i = 0; i < elements.length; i++) {{
            if (elements[i].textContent.includes('{text_to_find}')) {{
                elements[i].scrollIntoView({{behavior: 'smooth', block: 'center'}});
                return true;
            }}
        }}
        return false;
        """
        
        result = driver.execute_script(script)
        if result:
            print(f"Scrolled to text: '{text_to_find}'")
            time.sleep(1)
        else:
            print(f"Text not found: '{text_to_find}'")
        
    except Exception as e:
        print(f"Error scrolling to text: {e}")
    
    return {"success": True}

def main():
    """Optimized main function with better error handling and performance monitoring."""
    global driver
    
    print("DEBUG: Optimized main function started...")
    print("🚀 Hello! I am your AI Assistant with performance optimizations. How can I help you today?")
    print("Type 'exit' to quit or 'stats' to see performance statistics.")

    current_step_index = 0
    actual_steps = None

    try:
        while True:
            if current_step_index == 0:
                user_input = input("You: ").strip()
                
                if user_input.lower() == 'exit':
                    break
                elif user_input.lower() == 'stats':
                    stats = performance_monitor.get_stats()
                    memory_stats = memory_manager.get_memory_usage()
                    print(f"\n📊 Performance Statistics:")
                    for key, value in stats.items():
                        print(f"  {key}: {value}")
                    print(f"\n💾 Memory Usage:")
                    for key, value in memory_stats.items():
                        print(f"  {key}: {value:.2f}" + ("%" if "percent" in key else " GB" if "gb" in key else ""))
                    print(f"  Cache size: {vision_cache.size()} entries")
                    print()
                    continue
                
                if not gemini_api_key:
                    print("CRITICAL ERROR: API Key is not set in apikey.py. Please edit the file.")
                    break

                parsed_plan = get_gemini_plan(user_goal=user_input)

                if parsed_plan and isinstance(parsed_plan.get('steps'), list):
                    actual_steps = parsed_plan['steps']
                    print(f"\n📝 Here is the optimized plan ({len(actual_steps)} steps):")
                    for i, step_item in enumerate(actual_steps, 1):
                        action = step_item.get('action', 'Unknown')
                        print(f"  Step {i}: {action}")
                    print("\nAttempting to execute the plan...")
                else:
                    print("Sorry, I couldn't create a valid plan for that.\n")
                    actual_steps = None
                    continue

                shared_context['execution_halted'] = False
                current_step_index = 0

            if actual_steps and current_step_index < len(actual_steps):
                step_to_execute = actual_steps[current_step_index]

                if shared_context.get('execution_halted', False):
                    print("DEBUG: Plan execution was previously halted.")
                    current_step_index = 0
                    actual_steps = None
                    continue

                action_result_obj = execute_action(step_to_execute)

                if not action_result_obj.get("success", False) and action_result_obj.get("critical_error", False):
                    print("Halting plan execution due to critical error.")
                    current_step_index = 0
                    actual_steps = None
                    continue

                jump_target = action_result_obj.get("jump_to_step")
                if jump_target is not None:
                    target_0_indexed = jump_target - 1
                    if 0 <= target_0_indexed < len(actual_steps):
                        current_step_index = target_0_indexed
                    else:
                        print(f"DEBUG: Invalid jump target {jump_target}. Proceeding sequentially.")
                        current_step_index += 1
                else:
                    current_step_index += 1

                if current_step_index >= len(actual_steps):
                    print("✅ Finished executing all planned steps.")
                    current_step_index = 0
                    actual_steps = None
            else:
                current_step_index = 0
                actual_steps = None

    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        # Cleanup
        if driver and is_browser_alive(driver):
            print("Final cleanup: Returning browser to pool...")
            browser_pool.return_browser(driver)
        
        print("\n📊 Final Performance Statistics:")
        stats = performance_monitor.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        print("Goodbye!")

if __name__ == "__main__":
    print("DEBUG: Optimized script started...")
    main()