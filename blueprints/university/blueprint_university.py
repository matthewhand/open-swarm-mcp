# blueprints/university/blueprint_university.py

"""
University Support System Blueprint

Key Features:
- Multi-agent orchestration to handle various user queries.
- Structured routines with step tracking to manage agent interactions.
- Integration with SQLite via MCP for managing course and scheduling data.
- Demonstrates agent handoffs based on query context.
- Each agent has distinct instructions and response styles.
- Instructions are sourced from external .txt files if available, following a specific naming convention.
- Comprehensive debug statements and robust exception handling.
"""

import logging
import os
import sqlite3
import json
from typing import Dict, Any, Optional, List, Callable, Union

from swarm import Agent, Swarm
from swarm.repl import run_demo_loop
from swarm.extensions.blueprint import BlueprintBase

# Configure logging with detailed debug statements
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG to capture all levels of logs
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Type alias for agent-exposed function calls
AgentFunction = Callable[..., Union[Agent, str]]

# Constants for table names
SCHEDULER_TABLE = "schedules"
COURSE_ADVISOR_TABLE = "courses"


class UniversitySupportBlueprint(BlueprintBase):
    """
    University Support System Blueprint with multi-agent orchestration and handoffs.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """
        Initialize the UniversitySupportBlueprint.

        Args:
            config (Optional[Dict[str, Any]]): Configuration dictionary.
            **kwargs: Additional keyword arguments (e.g., model_override).
        """
        logger.debug("Initializing UniversitySupportBlueprint.")
        super().__init__(config=config, **kwargs)  # Pass config and any overrides to superclass

        logger.debug("Swarm client initialized.")
        self.client = Swarm()
        logger.info("University Support Blueprint initialized successfully.")

    @property
    def metadata(self):
        return {
            "title": "University Support System",
            "description": "Multi-agent system for university support using MCP tools.",
            "required_mcp_servers": ["sqlite"],  # Request the sqlite MCP server
            "env_vars": ["SQLITE_DB_PATH"],
        }

    def validate_env_vars(self) -> None:
        """Validate required environment variables and set up the SQLite database."""
        logger.debug("Validating environment variables.")
        sqlite_db_path = os.getenv("SQLITE_DB_PATH")
        if not sqlite_db_path:
            logger.error("Environment variable SQLITE_DB_PATH is not set.")
            raise EnvironmentError("SQLITE_DB_PATH environment variable is required.")

        logger.debug(f"SQLITE_DB_PATH found: {sqlite_db_path}")

    def _ensure_database_setup(self) -> None:
        """
        Ensures the SQLite database exists and is populated with required data.
        """
        logger.debug("Ensuring database setup.")
        sqlite_db_path = os.getenv("SQLITE_DB_PATH")
        db_exists = os.path.isfile(sqlite_db_path)

        if not db_exists:
           logger.info("SQLite database not found. Initiating database setup.")
           db_dir = os.path.dirname(sqlite_db_path)
           if db_dir and not os.path.isdir(db_dir):
               try:
                   logger.debug(f"Database directory {db_dir} does not exist. Creating directory.")
                   os.makedirs(db_dir, exist_ok=True)
                   logger.info(f"Database directory {db_dir} created successfully.")
               except Exception as e:
                   logger.exception(f"Failed to create database directory {db_dir}: {e}")
                   raise e
           else:
               logger.debug(f"Database directory {db_dir} already exists.")

           try:
                logger.debug(f"Connecting to SQLite database at {sqlite_db_path}.")
                conn = sqlite3.connect(sqlite_db_path)
                cursor = conn.cursor()

                # Create courses table
                logger.debug(f"Creating table {COURSE_ADVISOR_TABLE}.")
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {COURSE_ADVISOR_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        course_name TEXT NOT NULL,
                        description TEXT NOT NULL,
                        discipline TEXT NOT NULL
                    );
                """)
                logger.info(f"Table {COURSE_ADVISOR_TABLE} created successfully.")

                # Create schedules table
                logger.debug(f"Creating table {SCHEDULER_TABLE}.")
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {SCHEDULER_TABLE} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        course_name TEXT NOT NULL,
                        class_time TEXT NOT NULL,
                        exam_date TEXT NOT NULL
                    );
                """)
                logger.info(f"Table {SCHEDULER_TABLE} created successfully.")

                # Populate tables with sample data from separate SQL file
                sample_data_path = os.path.join(os.path.dirname(__file__), "sample_data.sql")
                if os.path.isfile(sample_data_path):
                    try:
                        logger.debug(f"Loading sample data from {sample_data_path}.")
                        with open(sample_data_path, 'r') as f:
                            sample_data = f.read()
                            cursor.executescript(sample_data)
                        logger.info("Sample data populated successfully.")
                    except Exception as e:
                        logger.exception(f"Failed to load sample data from {sample_data_path}: {e}")
                        raise e
                else:
                   logger.warning(f"Sample data file {sample_data_path} does not exist. Skipping data population.")


                conn.commit()
                logger.debug("Committing changes to the database.")
                conn.close()
                logger.info("SQLite database setup completed successfully.")
           except sqlite3.Error as db_err:
               logger.exception(f"SQLite error during database setup: {db_err}")
               raise db_err
           except Exception as e:
               logger.exception(f"Unexpected error during database setup: {e}")
               raise e
        else:
             logger.debug("SQLite database already exists. Skipping database setup.")


    def create_agents(self) -> None:
        """
        Create and configure agents for the University Support System.
        """
        logger.debug("Creating University Support agents.")

        # Directory where the blueprint is located
        blueprint_dir = os.path.dirname(__file__)
        logger.debug(f"Blueprint directory: {blueprint_dir}")

        # Helper function to load instructions from a file
        def load_instructions(agent_name: str) -> str:
            """
            Attempts to load agent instructions from an external .txt file.
            If the file does not exist or is unreadable, returns an empty string.
            """
            # Replace spaces with underscores for the filename
            agent_filename_part = agent_name.replace(" ", "_")
            instruction_filename = f"instructions_{agent_filename_part}.txt"
            instruction_path = os.path.join(blueprint_dir, instruction_filename)
            if os.path.isfile(instruction_path):
                try:
                    logger.debug(f"Loading instructions for {agent_name} from {instruction_filename}.")
                    with open(instruction_path, 'r') as file:
                        instructions = file.read()
                        logger.info(f"Instructions for {agent_name} loaded successfully from {instruction_filename}.")
                        return instructions
                except Exception as e:
                    logger.exception(f"Error reading {instruction_filename}: {e}")
            else:
                logger.warning(f"Instruction file {instruction_filename} not found for {agent_name}. Using hardcoded instructions.")
            return ""

        # Define hardcoded instructions for each agent
        hardcoded_instructions = {
            "TriageAgent": (
                "You are the Triage Agent, responsible for analysing user queries and directing them to the appropriate specialised agent. "
                "Evaluate the content and intent of each query to determine whether it pertains to course recommendations, campus culture, or scheduling assistance. "
                "Provide a brief reasoning before making the handoff to ensure transparency in your decision-making process. "
                "If a handoff is required, use the appropriate tool call for the target agent, such as `triage_to_course_advisor`, `triage_to_university_poet`, or `triage_to_scheduling_assistant`."
                "If the user says they want a haiku, you should set the 'response_haiku' variable to 'true'"
            ),
            "CourseAdvisor": (
                "You are the Course Advisor, dedicated to providing personalised course recommendations based on the user's academic interests and goals. "
                "Engage the user with insightful questions to understand their preferences, such as preferred disciplines, desired career paths, and previous coursework. "
                "Offer detailed explanations for each recommended course, highlighting how they align with the user's objectives. "
                "You have access to a tool named `read_query` which can be used to query data from an sqlite database, to better inform your advice, especially on what courses are available."
            ),
            "UniversityPoet": (
                "You are the University Poet, tasked with responding to queries about campus culture, events, and social activities in the form of creative haikus. "
                "Embrace a poetic and imaginative approach to provide concise and aesthetically pleasing responses that capture the essence of the university's vibrant community."
            ),
            "SchedulingAssistant": (
                "You are the Scheduling Assistant, responsible for managing and providing information about class schedules, exam dates, and important academic timelines. "
                "Interact with the user to ascertain their specific scheduling needs, such as course timings, exam schedules, and deadline dates. "
                "Offer clear, concise, and factual information to help users effectively plan their academic activities. "
                "You have access to a tool named `read_query` which can be used to query data from an sqlite database, to better inform your advice, especially on class schedules."
            )
        }

        # Create each agent and register with swarm
        agents = {}
        for agent_name, default_instructions in hardcoded_instructions.items():
            instructions = load_instructions(agent_name)
            if not instructions:
                instructions = default_instructions
                logger.debug(f"Using hardcoded instructions for {agent_name}.")

            # Define functions for each agent using self. methods (these functions use a context_variables dictionary):
            if agent_name == "TriageAgent":
                funcs = [
                    self._triage_to_course_advisor,
                    self._triage_to_university_poet,
                    self._triage_to_scheduling_assistant
                ]
            elif agent_name == "CourseAdvisor":
                funcs = [self._course_advisor_finalise]
            elif agent_name == "UniversityPoet":
                funcs = [self._university_poet_finalise]
            elif agent_name == "SchedulingAssistant":
                funcs = [self._scheduling_assistant_finalise]
            else:
                funcs = []
                logger.warning(f"No functions defined for agent {agent_name}.")

            try:
                agent = Agent(
                    name=agent_name,
                    instructions=instructions,
                    functions=funcs,
                    parallel_tool_calls=True,
                    mcp_servers = ["sqlite"] if agent_name in ["CourseAdvisor", "SchedulingAssistant"] else [] # Only add MCP if correct agent
                )
                self.swarm.create_agent(agent)
                agents[agent_name] = agent
                logger.info(f"Agent {agent_name} created successfully.")
            except Exception as e:
                logger.exception(f"Failed to create agent {agent_name}: {e}")
        logger.info("All University Support agents created.")


    def get_agents(self) -> Dict[str, Agent]:
        """Return dictionary of University Support agents."""
        logger.debug("Retrieving agents.")
        return self.swarm.agents  # Retrieve agents from swarm

    # =========================================
    # 1) Finalisation Functions
    # =========================================

    def _finalise_response(self, context_variables: dict) -> str:
        """
        Finalises the interaction with the user.
        """
        logger.debug("Finalising user interaction.")
        return json.dumps({"content":"Thank you for using the University Support System. If you have more questions, feel free to reach out!", "context_variables": context_variables})

    # =========================================
    # 2) Handoff Functions (as tool calls)
    # =========================================

    # TriageAgent handoff functions (now tool calls that return agent)
    def _triage_to_course_advisor(self, context_variables: dict) -> Agent:
        """
        Handoff to Course Advisor.
        """
        logger.debug("Handing off to Course Advisor.")
        return self.swarm.agents.get("CourseAdvisor")

    def _triage_to_university_poet(self, context_variables: dict) -> Agent:
        """
        Handoff to University Poet.
        """
        logger.debug("Handing off to University Poet.")
        return self.swarm.agents.get("UniversityPoet")

    def _triage_to_scheduling_assistant(self, context_variables: dict) -> Agent:
        """
        Handoff to Scheduling Assistant.
        """
        logger.debug("Handing off to Scheduling Assistant.")
        return self.swarm.agents.get("SchedulingAssistant")

    # CourseAdvisor handoff (finalisation) (now tool calls)
    def _course_advisor_finalise(self, context_variables: dict) -> str:
        """
        Finalise interaction from Course Advisor.
        """
        logger.debug("Course Advisor finalising interaction.")
        return json.dumps({"content": self._finalise_response(context_variables), "context_variables": context_variables})

    # UniversityPoet handoff (finalisation) (now tool calls)
    def _university_poet_finalise(self, context_variables: dict) -> str:
        """
        Finalise interaction from University Poet.
        """
        logger.debug("University Poet finalising interaction.")
        if context_variables.get('response_haiku') == 'true':
            logger.info(f"UniversityPoet will respond with a haiku. Context: {context_variables}")
            return json.dumps({"content": f"{self._university_poet_haiku()}", "context_variables": context_variables})
        else:
            logger.info(f"UniversityPoet will respond with a normal response. Context: {context_variables}")
            return json.dumps({"content": self._finalise_response(context_variables) , "context_variables": context_variables})

    def _university_poet_haiku(self) -> str:
        return f"""
            A student asks why,
            Campus calls with ancient tales,
            Wisdom finds its way.
            """

    # SchedulingAssistant handoff (finalisation) (now tool calls)
    def _scheduling_assistant_finalise(self, context_variables: dict) -> str:
        """
        Finalise interaction from Scheduling Assistant.
        """
        logger.debug("Scheduling Assistant finalising interaction.")
        return json.dumps({"content": self._finalise_response(context_variables), "context_variables": context_variables})

    # =========================================
    # 4) Framework Integration (execute)
    # =========================================

    def execute(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executes the blueprint's main functionality.
        """
        logger.debug("Executing blueprint main functionality.")
        try:
            self.validate_env_vars()
        except Exception as e:
            logger.critical(f"Environment variable validation failed: {e}")
            return {
                "status": "failure",
                "error": str(e),
                "metadata": self.metadata,
            }

        self._ensure_database_setup() # Ensure database exists

        try:
            user_query = input("How can I assist you today? ")
            logger.info(f"User Query Received: {user_query}")
        except Exception as e:
            logger.exception(f"Failed to receive user input: {e}")
            return {
                "status": "failure",
                "error": "Failed to receive user input.",
                "metadata": self.metadata,
            }

        # Initialise with Triage Agent
        starting_agent = self.swarm.agents.get("TriageAgent")
        if not starting_agent:
            logger.critical("TriageAgent not found. Cannot proceed with interaction.")
            return {
                "status": "failure",
                "error": "TriageAgent not found.",
                "metadata": self.metadata,
            }
        logger.info(f"Starting interaction with agent: {starting_agent.name}")

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_query}
        ]
        context_variables = {}
        active_agent = starting_agent
        while active_agent:
            logger.info(f"Calling agent: {active_agent.name}, with context: {context_variables}")
            try:
                logger.debug(f"Running Swarm client with agent: {active_agent.name}")
                response = self.client.run(agent=active_agent, messages=messages, context_variables=context_variables)
                logger.debug(f"Received response from agent: {active_agent.name}")
            except Exception as e:
                logger.exception(f"Error during Swarm run with agent {active_agent.name}: {e}")
                return {
                    "status": "failure",
                    "error": f"Error during interaction: {e}",
                    "metadata": self.metadata,
                }

            for message in response.messages:
                if isinstance(message, dict) and 'content' in message:
                    content = message['content']
                    logger.debug(f"Processing message content: {content}")

                    # Append the assistant's message to the conversation
                    messages.append(message)


            if response.agent:
                active_agent = response.agent
                logger.info(f"Handing off to agent: {active_agent.name}")
                if response.context_variables:
                   context_variables = response.context_variables
            elif any("Thank you for using the University Support System" in msg.get("content", "") for msg in messages):
                logger.info("Finalisation message detected. Ending interaction.")
                break
            else:
                logger.info("No further agents to handle the query. Ending interaction.")
                break



        return {
            "status": "success",
            "messages": messages,
            "metadata": self.metadata,
        }

    # =========================================
    # 5) Interactive Mode Override
    # =========================================

    def interactive_mode(self) -> None:
        """
        Overrides the default interactive mode to start with Triage Agent.
        """
        logger.debug("Entering interactive mode.")
        self._ensure_database_setup() # Ensure database exists

        starting_agent = self.swarm.agents.get("TriageAgent")
        if not starting_agent:
            logger.critical("TriageAgent not found. Cannot enter interactive mode.")
            return
        logger.info(f"Starting interactive mode with agent: {starting_agent.name}")
        try:
            run_demo_loop(starting_agent=starting_agent)
            logger.debug("Exited interactive mode successfully.")
        except Exception as e:
            logger.exception(f"Error during interactive mode: {e}")

# Entry point for standalone execution
if __name__ == "__main__":
    blueprint = UniversitySupportBlueprint()
    try:
        blueprint.interactive_mode()
    except Exception as e:
        print(f"Error running Default Blueprint: {e}")