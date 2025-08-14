# Multi-Worker AI Chat Orchestrator

This project is an advanced command-line interface (CLI) chat application that uses a multi-agent architecture to generate high-quality AI responses. Instead of relying on a single model response, it tasks multiple "Worker" agents to generate draft answers in parallel. A final "Synthesizer" agent then refines these drafts into a single, polished response.

The application features a rich, dynamic terminal UI powered by the `rich` library, providing real-time status updates on the agent's progress.



---

## Features

-   **Multi-Agent Architecture**: Leverages multiple parallel workers and a synthesizer for more robust and refined answers.
-   **Rich CLI**: A dynamic dashboard shows the real-time status of each worker and the synthesizer, complete with spinners and progress timers.
-   **Session Management**: Save and load your chat history to resume conversations later.
-   **Runtime Configuration**: Adjust settings like the model, reasoning level, and logging on-the-fly without restarting the script.
-   **Retry Logic**: Automatically retries failed API calls to handle transient network issues.
-   **Detailed Logging**: Optionally save a full trace of each turn—including all worker drafts and the final output—to a text file for analysis.

---

## How It Works

The script follows a simple yet powerful "Mixture of Experts" pattern for each user prompt:

1.  **Dispatch**: The user's message and the conversation history are sent to multiple Worker agents simultaneously using `asyncio`.
2.  **Draft**: Each Worker independently processes the request and generates a draft answer.
3.  **Synthesize**: The Synthesizer agent receives the original request and all the worker drafts. Its job is to analyze the drafts, merge the best ideas, resolve any conflicts, and produce one superior, final answer.
4.  **Display**: The final answer is printed to the console, and the turn is complete.

This approach helps mitigate weaknesses or hallucinations from a single model run and often results in more accurate and comprehensive responses.

---

## Installation & Setup

### Prerequisites

-   Python 3.8+
-   An OpenAI API key

### Steps

1.  **Clone or Download**:
    Save the script (`main.py`) to your local machine.

2.  **Install Dependencies**:
    The script requires the `openai` and `rich` libraries. Install them using pip:
    ```bash
    pip install openai rich
    ```

3.  **Set Environment Variable**:
    You must set your OpenAI API key as an environment variable.

    -   **macOS/Linux**:
        ```bash
        export OPENAI_API_KEY='your-api-key-here'
        ```
    -   **Windows (Command Prompt)**:
        ```bash
        set OPENAI_API_KEY=your-api-key-here
        ```
    -   **Windows (PowerShell)**:
        ```powershell
        $env:OPENAI_API_KEY="your-api-key-here"
        ```

---

## Usage

Run the script from your terminal:

```bash
python main.py
````

You will be greeted by the orchestrator's prompt. Simply type your message and press Enter.

### Commands

The application supports several slash commands:

  - `/settings`: Open the settings menu to change the model, reasoning level, or toggle file logging.
  - `/save <name>`: Saves the current conversation history to a JSON file in the `sessions/` directory. Example: `/save my_research_chat`
  - `/load <name>`: Loads a previous conversation. Example: `/load my_research_chat`
  - `/list`: Lists all saved sessions.
  - `/exit`: Quits the application.

-----

## Configuration

You can customize the script's behavior by editing the global variables at the top of the file:

  - `CURRENT_MODEL`: The default model to use (e.g., `"gpt-5"`).
  - `MODEL_CHOICES`: A list of models available to choose from in the settings menu.
  - `N_WORKERS`: The number of parallel workers to use for generating drafts.
  - `REASONING_LEVEL`: The default reasoning effort for the models.
  - `LOG_ALL_TO_FILE`: Set to `True` to enable detailed logging by default.

<!-- end list -->
