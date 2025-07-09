import google.generativeai as genai
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
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
from typing import Any, Dict, List, Union
import ast
import operator as op
import os

# --- MODIFICATION: Import the API key securely from the apikey.py file ---
from apikey import gemini_api_key

# --- Configuration ---
# The hardcoded API_KEY variable has been removed.
VISION_IMAGE_RESIZE_WIDTH = 1024
VISION_IMAGE_RESIZE_HEIGHT = 768


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

# Global variables
driver = None
WAIT_TIME = 10
vision_model_name = 'gemini-1.5-flash-latest'
vision_model = None
shared_context = {}
_PATH_NOT_FOUND_MARKER_STR = "[{path} not found/extracted]"
class _NotFoundType: pass
NOT_FOUND = _NotFoundType()
_OPERATORS = {
    '==': op.eq,
    '!=': op.ne,
    '>': op.gt,
    '<': op.lt,
    '>=': op.ge,
    '<=': op.le,
}

def strip_json_comments(json_text: str) -> str:
    if json_text is None: return ""
    lines = json_text.splitlines()
    cleaned_lines = []
    for line in lines:
        if not line.strip().startswith("//"):
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def sanitize_json_string_for_loading(s: str) -> str:
    if s is None: return ""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', s)

def get_gemini_plan(user_goal: str): # Function definition
    global shared_context
    shared_context = {}
    print("DEBUG: get_gemini_plan function called (shared_context reset).")

    try:
        direct_plan = json.loads(user_goal)
        if isinstance(direct_plan, dict) and "steps" in direct_plan:
            print("DEBUG: User input is valid JSON plan. Using it directly.")
            return direct_plan
    except json.JSONDecodeError:
        print("DEBUG: User input is not a direct JSON plan. Proceeding to LLM for planning.")
        pass

    print("🧠 Assistant is thinking...")
    json_string_for_parsing = None
    text_after_markdown_strip = None
    raw_response_text = None
    try:
        # --- MODIFICATION: Use the imported key ---
        if not gemini_api_key:
            print("ERROR: API_KEY is not set in apikey.py or is empty.")
            return None
        genai.configure(api_key=gemini_api_key)
        planning_model = genai.GenerativeModel('gemini-1.5-pro-latest')
        print("DEBUG: Planning model configured successfully.")

        full_prompt = PROMPT_TEMPLATE.format(user_goal=user_goal)

        print("DEBUG: Sending prompt to Gemini for planning...")
        response = planning_model.generate_content(full_prompt)
        print("DEBUG: Received planning response from Gemini.")

        raw_response_text = response.text.strip()
        print(f"DEBUG: Raw response text from Gemini (before any cleaning):\n---\n{raw_response_text}\n---")

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
        problem_text_snippet = "N/A"
        text_that_failed = json_string_for_parsing if json_string_for_parsing else raw_response_text
        if text_that_failed:
            error_pos = e.pos
            start = max(0, error_pos - 100)
            end = min(len(text_that_failed), error_pos + 100)
            problem_text_snippet = text_that_failed[start:end]
        print(f"DEBUG: Problematic text snippet for JSON parsing: ...{problem_text_snippet}...")
        return None
    except Exception as e:
        print(f"DEBUG: Exception in get_gemini_plan: {str(e)} (Type: {type(e).__name__})")
        return None

def get_selenium_by(locator_type_str: str):
    if locator_type_str == "id": return By.ID
    elif locator_type_str == "name": return By.NAME
    elif locator_type_str == "xpath": return By.XPATH
    elif locator_type_str == "css_selector": return By.CSS_SELECTOR
    elif locator_type_str == "class_name": return By.CLASS_NAME
    elif locator_type_str == "link_text": return By.LINK_TEXT
    elif locator_type_str == "partial_link_text": return By.PARTIAL_LINK_TEXT
    else:
        print(f"Warning: Unknown locator type '{locator_type_str}'. Defaulting to By.ID.")
        return By.ID

def is_browser_alive(driver_instance):
    if driver_instance is None: return False
    try:
        _ = driver_instance.title
        return True
    except (NoSuchWindowException, InvalidSessionIdException, WebDriverException) as e:
        print(f"DEBUG: Browser session appears to be dead or unresponsive. Error: {type(e).__name__} - {e}")
        return False

def _get_value_from_path(context: Dict[str, Any], path_expression: str) -> Any:
    if not isinstance(path_expression, str) or not path_expression or not isinstance(context, dict):
        return NOT_FOUND
    m = re.match(r"^\s*([a-zA-Z_]\w*)", path_expression)
    if not m:
        if path_expression.strip() in context:
            return context[path_expression.strip()]
        return NOT_FOUND
    var_name = m.group(1)
    if var_name not in context:
        return NOT_FOUND
    current = context[var_name]
    remainder = path_expression[m.end():].strip()
    token_pattern = re.compile(r"""
        ^\s*(?:
            (?:\.\s*([a-zA-Z_]\w*))
          | (?:\[\s*(
                (-?\d+)
              | (?:(?P<quote_char>['"])(.*?)(?P=quote_char))
              )\s*\])
        )
    """, re.VERBOSE)
    temp_remaining_path = remainder
    current_value_for_loop = current
    while temp_remaining_path:
        token_match = token_pattern.match(temp_remaining_path)
        if not token_match:
            if temp_remaining_path.strip():
                print(f"DEBUG: _get_value_from_path: Invalid path segment at: '{temp_remaining_path}' in '{path_expression}'")
            return NOT_FOUND
        dot_attr = token_match.group(1)
        numeric_idx_str = token_match.group(2)
        bracket_str_key = token_match.group(4)
        if dot_attr is not None:
            if isinstance(current_value_for_loop, dict):
                if dot_attr in current_value_for_loop: current_value_for_loop = current_value_for_loop[dot_attr]
                else: print(f"DEBUG: _get_value_from_path (dot): Key '{dot_attr}' missing in dict. Path: '{path_expression}'"); return NOT_FOUND
            else: print(f"DEBUG: _get_value_from_path (dot): Trying to access key '{dot_attr}' but current_value is {type(current_value_for_loop)}"); return NOT_FOUND
        elif numeric_idx_str is not None:
            try:
                idx_int = int(numeric_idx_str)
                if isinstance(current_value_for_loop, list):
                    if -len(current_value_for_loop) <= idx_int < len(current_value_for_loop): current_value_for_loop = current_value_for_loop[idx_int]
                    else: print(f"DEBUG: _get_value_from_path (index): Index {idx_int} out of range. Path: '{path_expression}'"); return NOT_FOUND
                else: print(f"DEBUG: _get_value_from_path (index): Trying to index a non-list. Path: '{path_expression}'"); return NOT_FOUND
            except ValueError: print(f"DEBUG: _get_value_from_path (index): Invalid integer '{numeric_idx_str}'. Path: '{path_expression}'"); return NOT_FOUND
        elif bracket_str_key is not None:
            if isinstance(current_value_for_loop, dict):
                if bracket_str_key in current_value_for_loop: current_value_for_loop = current_value_for_loop[bracket_str_key]
                else: print(f"DEBUG: _get_value_from_path (bracket_key): Key '{bracket_str_key}' not found. Path: '{path_expression}'"); return NOT_FOUND
            else: print(f"DEBUG: _get_value_from_path (bracket_key): Trying to access key on non-dict. Path: '{path_expression}'"); return NOT_FOUND
        else: print(f"DEBUG: _get_value_from_path - Unhandled token. Path: '{path_expression}'"); return NOT_FOUND
        temp_remaining_path = temp_remaining_path[token_match.end():].strip()
    if temp_remaining_path.strip():
        print(f"DEBUG: _get_value_from_path - Unconsumed parts for '{path_expression}'. Unparsed: '{temp_remaining_path}'")
        return NOT_FOUND
    return current_value_for_loop

def _resolve_placeholders(template_string: str, context: dict) -> str:
    if not isinstance(template_string, str): return template_string
    def replacer(match):
        ph_full_path = match.group(1).strip()
        val = _get_value_from_path(context, ph_full_path)
        if val is NOT_FOUND: return _PATH_NOT_FOUND_MARKER_STR.format(path=ph_full_path)
        elif val is None: return "None"
        elif isinstance(val, list):
            if not val: return "[empty list]"
            return ", ".join(map(str, val))
        else: return str(val)
    return re.sub(r"\{([^\{\}]+)\}", replacer, template_string)

def _evaluate_condition(condition_template: str, context: Dict[str, Any]) -> bool:
    def evaluate_single_comparison(comp_str):
        length_pattern = r"\{([^\{\}]+?)\}\.length\s*(==|!=|<=|>=|<|>)\s*(\d+)"
        length_match = re.fullmatch(length_pattern, comp_str.strip())
        if length_match:
            list_path, op_str, val_str = length_match.groups()
            list_val = _get_value_from_path(context, list_path.strip())
            if not isinstance(list_val, list): return False
            return _OPERATORS[op_str](len(list_val), int(val_str))
        comp_pattern = r"(.+?)(==|!=|<=|>=|<|>)(.+)"
        match = re.match(comp_pattern, comp_str)
        if not match: return bool(_get_value_from_path(context, comp_str.strip()))
        left_str, op_str, right_str = match.groups()
        left = _resolve_placeholders(left_str.strip(), context)
        right = _resolve_placeholders(right_str.strip(), context)
        try:
            num_left, num_right = float(left), float(right)
            return _OPERATORS[op_str](num_left, num_right)
        except (ValueError, TypeError):
            return _OPERATORS[op_str](str(left), str(right))
    normalized_condition = condition_template.replace("{{", "{").replace("}}", "}")
    if "||" in normalized_condition:
        return any(evaluate_single_comparison(part) for part in normalized_condition.split("||"))
    if "&&" in normalized_condition:
        return all(evaluate_single_comparison(part) for part in normalized_condition.split("&&"))
    return evaluate_single_comparison(normalized_condition)


def execute_action(step):
    global driver
    global vision_model
    global shared_context

    action_type = step.get("action")
    action_data = step.get("data", {})

    if action_type == "OPEN_BROWSER":
        if driver is not None and is_browser_alive(driver):
            print("DEBUG: Browser already open. Skipping OPEN_BROWSER.")
            return {"success": True}
        try:
            service = ChromeService()
            driver = webdriver.Chrome(service=service)
            print("Opened Chrome browser successfully.")
            time.sleep(1)
        except Exception as e:
            print(f"Error opening Chrome browser: {e}")
            driver = None
            return {"success": False, "critical_error": True}
        return {"success": True}

    if not is_browser_alive(driver) and action_type not in ["ANSWER_USER", "OPEN_BROWSER"]:
        print(f"Browser session is dead. Cannot execute action: {action_type}.")
        shared_context['execution_halted'] = True
        return {"success": False, "critical_error": True}

    print(f"Executing action: {action_type} with data: {json.dumps(action_data)}")

    if action_type == "LABEL_AND_READ_SCREEN":
        context_key = action_data.get("context_key_to_store_labels", "last_labeled_elements")
        print(f"Executing LABEL_AND_READ_SCREEN. Storing results in context key: '{context_key}'")
        try:
            screenshot_bytes = driver.get_screenshot_as_png()
            img = Image.open(BytesIO(screenshot_bytes))
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
            if vision_model is None:
                print(f"DEBUG: Initializing vision model: {vision_model_name}")
                # --- MODIFICATION: Use the imported key ---
                genai.configure(api_key=gemini_api_key)
                vision_model = genai.GenerativeModel(vision_model_name)
            
            print("DEBUG: Sending screenshot to Gemini for element labeling...")
            image_part = {"mime_type": "image/png", "data": screenshot_bytes}
            prompt_parts = [vision_prompt, image_part]
            vision_response = vision_model.generate_content(prompt_parts)
            extracted_text = vision_response.text

            print(f"🤖 Vision Model Response for labels:\n---\n{extracted_text}\n---")
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", extracted_text, re.DOTALL)
            json_str = json_match.group(1).strip() if json_match else extracted_text
            labeled_elements_data = json.loads(json_str)
            elements_map = {item['number']: item for item in labeled_elements_data.get('elements', [])}

            shared_context[context_key] = elements_map
            print(f"Successfully labeled {len(elements_map)} elements and stored in context['{context_key}'].")

            draw = ImageDraw.Draw(img)
            try:
                font_path = "arial.ttf"
                font = ImageFont.truetype(font_path, 16)
            except IOError:
                print("Warning: Arial font not found. Using default font for labels.")
                font = ImageFont.load_default()

            for number, element in elements_map.items():
                box = element.get('box')
                if not box or len(box) != 4: continue
                draw.rectangle(box, outline="red", width=3)
                label_pos = (box[0], box[1] - 20 if box[1] > 20 else box[1])
                text_bbox = draw.textbbox(label_pos, str(number), font=font)
                draw.rectangle((text_bbox[0]-2, text_bbox[1]-2, text_bbox[2]+2, text_bbox[3]+2), fill="red")
                draw.text(label_pos, str(number), fill="white", font=font)

            labeled_screenshot_path = "screenshot_with_labels.png"
            img.save(labeled_screenshot_path)
            print(f"Saved labeled screenshot to '{labeled_screenshot_path}'.")
            shared_context[f"{context_key}_summary"] = f"Found and labeled {len(elements_map)} elements. See screenshot_with_labels.png for details."
        except Exception as e:
            print(f"Error during LABEL_AND_READ_SCREEN: {e}")
            return {"success": False}
        return {"success": True}

    elif action_type == "CLICK_ELEMENT" or action_type == "TYPE_INTO_ELEMENT":
        locator_data = action_data.get("locator", {})
        locator_type = locator_data.get("type")
        locator_value = locator_data.get("value")

        if locator_type == "label_number":
            context_source = locator_data.get("context_source")
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
            click_x = (box[0] + box[2]) // 2
            click_y = (box[1] + box[3]) // 2
            try:
                actions = ActionChains(driver)
                actions.move_by_offset(click_x, click_y).click().move_by_offset(-click_x, -click_y).perform()
                print(f"Performed click on labeled element '{locator_value}' at approx ({click_x}, {click_y}).")
                if action_type == "TYPE_INTO_ELEMENT":
                    text_to_type_template = action_data.get("text", "")
                    text_to_type = _resolve_placeholders(text_to_type_template, shared_context)
                    typing_actions = ActionChains(driver)
                    typing_actions.send_keys(text_to_type).perform()
                    print(f"Typed '{text_to_type}' into labeled element '{locator_value}'.")
                    if action_data.get("submit_after_typing"):
                        ActionChains(driver).send_keys(Keys.ENTER).perform()
                        print("Submitted form by pressing Enter.")
                time.sleep(1)
                return {"success": True}
            except Exception as e:
                print(f"Error interacting with labeled element '{locator_value}': {e}")
                return {"success": False}
        else:
            locator_value_resolved = _resolve_placeholders(str(locator_value), shared_context)
            if not all([locator_type, locator_value_resolved]):
                print(f"Missing locator_type or resolved locator_value for {action_type}.")
                return {"success": True, "skipped": True}
            try:
                by_type = get_selenium_by(locator_type)
                if action_type == "CLICK_ELEMENT":
                    element = WebDriverWait(driver, WAIT_TIME).until(EC.element_to_be_clickable((by_type, locator_value_resolved)))
                    element.click()
                    print(f"Clicked element found by {locator_type}: '{locator_value_resolved}'")
                elif action_type == "TYPE_INTO_ELEMENT":
                    element = WebDriverWait(driver, WAIT_TIME).until(EC.visibility_of_element_located((by_type, locator_value_resolved)))
                    text_to_type_template = action_data.get("text", "")
                    text_to_type = _resolve_placeholders(text_to_type_template, shared_context)
                    element.clear()
                    element.send_keys(text_to_type)
                    print(f"Typed '{text_to_type}' into element found by {locator_type}: '{locator_value_resolved}'")
                    if action_data.get("submit_after_typing"):
                        element.send_keys(Keys.ENTER)
                        print("Submitted form by pressing Enter.")
                time.sleep(2)
                return {"success": True}
            except TimeoutException:
                print(f"Timeout: Element not found/visible/clickable for {action_type} ({locator_type}='{locator_value_resolved}')")
                return {"success": True, "skipped": True}
            except Exception as e:
                print(f"Error in {action_type}: {e}")
                return {"success": False}

    elif action_type == "NAVIGATE_TO_URL":
        url_template = action_data.get("url")
        url = _resolve_placeholders(url_template, shared_context)
        if url and not _PATH_NOT_FOUND_MARKER_STR.format(path='')[:-1] in url:
            driver.get(url)
            print(f"Navigated to URL: {url}")
            time.sleep(1)
        else:
            print(f"Skipping navigation due to unresolved placeholder in URL: {url_template}")
        return {"success": True}

    elif action_type == "READ_SCREEN":
        custom_vision_prompt = action_data.get("prompt_for_vision", "Describe what you see.")
        context_key_to_store = action_data.get("context_key_to_store", "last_vision_response")
        try:
            screenshot_bytes = driver.get_screenshot_as_png()
            if vision_model is None:
                # --- MODIFICATION: Use the imported key ---
                genai.configure(api_key=gemini_api_key)
                vision_model = genai.GenerativeModel(vision_model_name)
            image_part = {"mime_type": "image/png", "data": screenshot_bytes}
            prompt_parts = [custom_vision_prompt, image_part]
            vision_response = vision_model.generate_content(prompt_parts)
            shared_context[context_key_to_store] = vision_response.text
            print(f"Stored vision response in '{context_key_to_store}': {vision_response.text[:150]}...")
        except Exception as e:
            print(f"Error in READ_SCREEN: {e}")
        return {"success": True}

    elif action_type == "ANSWER_USER":
        response_template = action_data.get("response_template", "Task completed.")
        final_answer = _resolve_placeholders(response_template, shared_context)
        print(f"\n🤖 Assistant to User: {final_answer}\n")
        return {"success": True}

    elif action_type == "CONDITIONAL_JUMP":
        condition_template = action_data.get("condition")
        goto_step = action_data.get("goto_step")
        if not condition_template or goto_step is None:
            return {"success": True}
        if _evaluate_condition(condition_template, shared_context):
            return {"success": True, "jump_to_step": int(goto_step)}
        return {"success": True}

    else:
        print(f"Unknown or not-yet-implemented action type: {action_type}")
        return {"success": True, "skipped": True}

def main():
    global driver
    print("DEBUG: Main function started...")
    print("Hello! I am your AI Assistant. How can I help you today?")
    print("Type 'exit' to quit.")

    current_step_index = 0
    actual_steps = None

    while True:
        if current_step_index == 0:
            user_input = input("You: ")
            if user_input.lower() == 'exit':
                if driver and is_browser_alive(driver):
                    print("Closing browser...")
                    driver.quit()
                print("Goodbye!")
                break
            
            # --- MODIFICATION: Use the imported key ---
            if not gemini_api_key:
                print("CRITICAL ERROR: API Key is not set in apikey.py. Please edit the file.")
                break

            parsed_plan = get_gemini_plan(user_goal=user_input)

            if parsed_plan and isinstance(parsed_plan.get('steps'), list):
                actual_steps = parsed_plan['steps']
                print("\n📝 Here is the plan I came up with:")
                for i, step_item in enumerate(actual_steps, 1):
                    print(f"  Step {i}: {step_item.get('action')} - {json.dumps(step_item.get('data', {}))}")
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
                print("Finished executing all planned steps.")
                current_step_index = 0
                actual_steps = None
        else:
            current_step_index = 0
            actual_steps = None

    if driver and is_browser_alive(driver):
        print("Final cleanup: Closing browser...")
        driver.quit()

if __name__ == "__main__":
    print("DEBUG: Script started...")
    main()
