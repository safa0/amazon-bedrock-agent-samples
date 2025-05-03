import argparse
import sys
from src.utils.bedrock_agent_helper import AgentsForAmazonBedrock

def create_agent(agents, name, description, instructions, models, collaboration_type):
    """Create an agent without preparing it"""
    agent_id, alias_id, alias_arn = agents.create_agent(
        agent_name=name,
        agent_description=description,
        agent_instructions=instructions,
        model_ids=models,
        agent_collaboration=collaboration_type
    )
    agents.wait_agent_status_update(agent_id=agent_id)
    return agent_id, alias_id, alias_arn

def main():
    parser = argparse.ArgumentParser(description="Joke Agent CLI")
    parser.add_argument("--recreate_agents", choices=['true','false'], default='true',
                        help="Whether to recreate the agent (true) or reuse existing (false)")
    args = parser.parse_args()

    if args.recreate_agents.lower() != 'true':
        print("This script only supports creating new agents at the moment")
        sys.exit(1)

    agents = AgentsForAmazonBedrock()
    foundation_models = [
        'anthropic.claude-3-sonnet-20240229-v1:0',
        'anthropic.claude-3-5-sonnet-20240620-v1:0',
        'anthropic.claude-3-haiku-20240307-v1:0'
    ]

    # Step 1: Create the leaf agent (joke agent) first with DISABLED collaboration
    joke_name = "joke_agent_1"
    joke_description = "Interactive Joke-telling Agent"
    joke_instructions = (
        "You are a playful AI that tells jokes. "
        "On each user query, respond with a single, funny joke related to the prompt."
    )
    
    joke_agent_id, joke_agent_alias_id, joke_agent_arn = create_agent(
        agents, joke_name, joke_description, joke_instructions, 
        foundation_models, "DISABLED"
    )
    
    # Step 2: Prepare the joke agent since it's a leaf node
    agents.prepare(agent_name=joke_name)
    agents.wait_agent_status_update(agent_id=joke_agent_id)
    
    # Step 3: Create an alias for the joke agent for collaboration
    joke_alias_id, joke_alias_arn = agents.create_agent_alias(
        agent_id=joke_agent_id, 
        alias_name="joke-alias"
    )
    
    # Step 4: Create the supervisor agent (unprepared) with SUPERVISOR type
    supervisor_name = "joke_supervisor_agent_1"
    supervisor_description = "Supervisor agent that coordinates with the joke agent"
    supervisor_instructions = (
        "You are a supervisor agent that handles requests from users. "
        "Your job is to forward all requests to the joke agent and relay the responses back to the user. "
        "Do not modify the responses from the joke agent. Simply relay exactly what the joke agent responds with."
    )
    
    supervisor_agent_id, supervisor_agent_alias_id, supervisor_agent_arn = create_agent(
        agents, supervisor_name, supervisor_description, supervisor_instructions, 
        foundation_models, "SUPERVISOR"
    )
    
    # Step 5: Set up the collaboration hierarchy
    sub_agent_list = [
        {
            "sub_agent_alias_arn": joke_alias_arn,
            "sub_agent_instruction": "You are a joke agent. Generate funny jokes based on user prompts.",
            "sub_agent_association_name": joke_name,
            "relay_conversation_history": "DISABLED"
        }
    ]
    
    # Step 6: Associate sub-agents with the supervisor
    agents.associate_sub_agents(supervisor_agent_id, sub_agent_list)
    agents.wait_agent_status_update(agent_id=supervisor_agent_id)
    
    # Step 7: Finally, prepare the supervisor agent
    agents.prepare(agent_name=supervisor_name)
    agents.wait_agent_status_update(agent_id=supervisor_agent_id)
    
    print(f"Joke Agent ready! (ID: {joke_agent_id}, Alias: {joke_agent_alias_id})")
    print(f"Supervisor Agent ready! (ID: {supervisor_agent_id}, Alias: {supervisor_agent_alias_id})")
    print("Type your prompt and hit Enter. Type 'exit' or 'quit' to stop.")
    print("Type 'supervisor:' before your prompt to use the supervisor agent.")

    while True:
        try:
            prompt = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            sys.exit(0)

        if prompt.strip().lower() in {'exit', 'quit'}:
            print("Goodbye!")
            break

        # Determine which agent to use
        if prompt.lower().startswith('supervisor:'):
            agent_id = supervisor_agent_id
            agent_alias_id = supervisor_agent_alias_id
            # Remove the 'supervisor:' prefix
            prompt = prompt[len('supervisor:'):].strip()
            agent_name = "Supervisor Agent"
        else:
            agent_id = joke_agent_id
            agent_alias_id = joke_agent_alias_id
            agent_name = "Joke Agent"

        # Invoke the selected agent and print response
        result = agents.invoke(
            input_text=prompt,
            agent_id=agent_id,
            agent_alias_id=agent_alias_id
        )
        print(f"{agent_name}: {result}\n")

if __name__ == '__main__':
    main()
