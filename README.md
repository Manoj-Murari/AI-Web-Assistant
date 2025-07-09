# Project Mini: Your Personal AI Web Agent

**Mini is an autonomous AI agent designed to understand and execute complex, multi-step tasks across the web. It moves beyond simple scripts by using a state-of-the-art vision-language model to see and interact with websites just like a human does.**

This project is the foundational step towards a true personal AI assistant that can handle real-world tasks like booking travel, managing online shopping, and gathering complex information, all from a single natural language command.

---

## 🚀 Core Features

* **🧠 Advanced AI Planning:** Leverages the **Google Gemini Pro** model to dynamically generate sophisticated, step-by-step plans from high-level user goals.
* **👁️ Vision-Powered Interaction:** Instead of relying on brittle selectors, Mini uses **Gemini Vision** to analyze screenshots, identify all interactive elements, and decide the best course of action. This allows it to adapt to almost any website layout without prior training.
* **🤖 Autonomous Execution:** Once a plan is formulated, the agent uses **Selenium** to execute it, navigating, clicking, and typing with human-like precision.
* **💡 Stateful & Context-Aware:** The agent maintains a `shared_context` to remember information across different steps and pages, enabling it to perform complex tasks that require memory (e.g., using a search result on a subsequent page).
* **🔍 Visual Debugging:** For every vision-based step, the agent saves a `screenshot_with_labels.png` file, providing a clear visual audit trail of what the AI "saw" and how it made its decisions.
* **🔐 Secure by Design:** All secret API keys are handled securely using a `.gitignore` file to prevent accidental exposure in the repository.

---

## 🛠️ How It Works: The Cognitive Cycle

Mini operates on a cognitive cycle that mimics human problem-solving:

1.  **Understand:** The user provides a high-level goal in natural language (e.g., "Find the price of an iPhone 13 on Flipkart").
2.  **Plan:** The **Gemini Pro** model acts as the "executive brain," breaking down the goal into a logical, step-by-step JSON plan.
3.  **Observe:** The agent navigates to a URL and uses the **Gemini Vision** model to take a "look" at the screen, identifying and labeling all buttons, links, and input fields.
4.  **Act:** Based on the plan, the agent executes the next step, such as clicking on a visually identified element or typing into a search bar.
5.  **Repeat:** The cycle continues—observing the new screen and acting—until the plan is complete.
6.  **Report:** The agent provides the final answer back to the user.

---

## 🌟 Future Vision & Roadmap

This project is the cornerstone of a much larger vision. The goal is to scale Mini into a fully-fledged personal AI agent capable of handling complex, real-world digital tasks. The roadmap includes:

* **🛒 E-commerce & Shopping:**
    * **Goal:** "Find me the best deal on a 65-inch 4K TV and add it to my cart."
    * **Functionality:** Price comparison across multiple sites, applying filters, and managing a shopping cart.
* **✈️ Travel & Booking:**
    * **Goal:** "Book the cheapest flight from Delhi to Mumbai for next weekend."
    * **Functionality:** Interacting with complex date-pickers, filling out passenger forms, and navigating booking portals on sites like IRCTC or MakeMyTrip.
* **📊 Data Gathering & Research:**
    * **Goal:** "Compile a list of the top 5 rated laptops under ₹80,000 from three different tech review sites."
    * **Functionality:** Advanced information extraction, data aggregation, and summarization.
* **🧠 Enhanced Memory & Learning:**
    * Implement a vector database (like Pinecone or ChromaDB) to give the agent long-term memory, allowing it to learn from past interactions and improve its strategies over time.
* **🗣️ Voice-Activated Interface:**
    * Integrate the agent with a voice-to-text and text-to-speech engine to create a fully conversational, hands-free experience.

---

## 💻 Technologies Used

* **Core Language:** Python
* **AI & Machine Learning:** Google Gemini Pro, Google Gemini Vision
* **Web Automation & Scraping:** Selenium
* **Image Processing:** Pillow
* **Development Environment:** Visual Studio Code

---

## ▶️ How to Run

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/Manoj-Murari/AI-Web-Assistant.git](https://github.com/Manoj-Murari/AI-Web-Assistant.git)
    cd AI-Web-Assistant
    ```
2.  **Setup Virtual Environment:**
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```
3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: You will need to create a `requirements.txt` file from your current setup using `pip freeze > requirements.txt`)*

4.  **Add API Key:**
    * Create a file named `apikey.py`.
    * Add your Gemini API key to it: `gemini_api_key = "YOUR_SECRET_KEY"`

5.  **Execute the Agent:**
    ```bash
    python main.py
    ```

---

*This project demonstrates a cutting-edge approach to web automation, moving beyond traditional methods to a more intelligent, adaptable, and human-like system. I am actively developing its capabilities and am excited about its potential to redefine personal digital assistance.*
