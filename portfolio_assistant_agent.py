import argparse
import sys
import time
import boto3
from src.utils.bedrock_agent_helper import AgentsForAmazonBedrock

def cleanup_agents(agents, agent_names):
    """Clean up agents in the correct order - supervisors first, then sub-agents"""
    print("Cleaning up existing agents...")
    
    # First, disassociate all collaborators from supervisor agents
    for name in agent_names:
        if 'portfolio' in name.lower():
            try:
                agent_id = agents.get_agent_id_by_name(name)
                if agent_id:
                    print(f"Disassociating collaborators from supervisor agent {name}...")
                    try:
                        # Update the agent to remove collaborator configuration
                        agents._bedrock_agent_client.update_agent(
                            agentId=agent_id,
                            agentVersion="DRAFT",
                            agentCollaboration="DISABLED"
                        )
                        agents.wait_agent_status_update(agent_id=agent_id)
                    except Exception as e:
                        print(f"Error disassociating collaborators from {name}: {e}")
            except Exception as e:
                print(f"Error accessing supervisor agent {name}: {e}")
    
    # Then delete supervisor agents
    for name in agent_names:
        if 'portfolio' in name.lower():
            try:
                agent_id = agents.get_agent_id_by_name(name)
                if agent_id:
                    print(f"Deleting supervisor agent {name}...")
                    # Delete all aliases first
                    aliases = agents._bedrock_agent_client.list_agent_aliases(agentId=agent_id)
                    for alias in aliases.get('agentAliasSummaries', []):
                        print(f"Deleting alias {alias['agentAliasId']} for agent {name}")
                        try:
                            agents._bedrock_agent_client.delete_agent_alias(
                                agentId=agent_id,
                                agentAliasId=alias['agentAliasId']
                            )
                        except Exception as e:
                            print(f"Error deleting alias {alias['agentAliasId']}: {e}")
                    
                    # Delete the agent
                    try:
                        agents._bedrock_agent_client.delete_agent(agentId=agent_id)
                        print(f"Successfully deleted supervisor agent {name}")
                    except Exception as e:
                        print(f"Error deleting supervisor agent {name}: {e}")
            except Exception as e:
                print(f"Error accessing supervisor agent {name}: {e}")
    
    # Finally delete sub-agents
    for name in agent_names:
        if 'portfolio' not in name.lower():
            try:
                agent_id = agents.get_agent_id_by_name(name)
                if agent_id:
                    print(f"Deleting sub-agent {name}...")
                    # Delete all aliases first
                    aliases = agents._bedrock_agent_client.list_agent_aliases(agentId=agent_id)
                    for alias in aliases.get('agentAliasSummaries', []):
                        print(f"Deleting alias {alias['agentAliasId']} for agent {name}")
                        try:
                            agents._bedrock_agent_client.delete_agent_alias(
                                agentId=agent_id,
                                agentAliasId=alias['agentAliasId']
                            )
                        except Exception as e:
                            print(f"Error deleting alias {alias['agentAliasId']}: {e}")
                    
                    # Delete the agent
                    try:
                        agents._bedrock_agent_client.delete_agent(agentId=agent_id)
                        print(f"Successfully deleted sub-agent {name}")
                    except Exception as e:
                        print(f"Error deleting sub-agent {name}: {e}")
            except Exception as e:
                print(f"Error accessing sub-agent {name}: {e}")
    
    # Clean up guardrail if exists
    bedrock_client = boto3.client("bedrock")
    try:
        response = bedrock_client.list_guardrails()
        for guardrail in response.get("guardrails", []):
            if guardrail["name"] == "no_bitcoin_guardrail":
                print(f"Found guardrail: {guardrail['id']}")
                guardrail_identifier = guardrail["id"]
                bedrock_client.delete_guardrail(guardrailIdentifier=guardrail_identifier)
                print("Successfully deleted guardrail")
    except Exception as e:
        print(f"Error cleaning up guardrail: {e}")

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

def get_lambda_arn(name, region, account_id):
    """Get the ARN of an existing Lambda function if it exists"""
    lambda_client = boto3.client('lambda')
    try:
        response = lambda_client.get_function(FunctionName=name)
        return response['Configuration']['FunctionArn']
    except Exception:
        # If the Lambda doesn't exist, return the constructed ARN
        return f"arn:aws:lambda:{region}:{account_id}:function:{name}"

def main():
    parser = argparse.ArgumentParser(description="Portfolio Assistant Agent CLI")
    parser.add_argument("--recreate_agents", choices=['true','false'], default='true',
                        help="Whether to recreate the agent (true) or reuse existing (false)")
    parser.add_argument("--clean_up", choices=['true','false'], default='false',
                        help="Clean up all agents and exit")
    parser.add_argument("--ticker", default="AMZN", help="The stock ticker to analyze")
    parser.add_argument("--trace_level", default="core", choices=['core', 'outline', 'all'],
                       help="The level of trace information to display")
    args = parser.parse_args()

    agents = AgentsForAmazonBedrock()
    
    # Get AWS region and account ID for Lambda ARNs
    boto_session = boto3.session.Session()
    region = boto_session.region_name
    account_id = boto3.client('sts').get_caller_identity().get('Account')
    
    # Agent names
    news_agent_name = "news_agent"
    stock_data_agent_name = "stock_data_agent"
    analyst_agent_name = "analyst_agent"
    portfolio_assistant_name = "portfolio_assistant"
    
    agent_names = [portfolio_assistant_name, news_agent_name, stock_data_agent_name, analyst_agent_name]

    # Handle cleanup
    if args.clean_up.lower() == 'true':
        cleanup_agents(agents, agent_names)
        print("Cleanup completed")
        sys.exit(0)

    # Foundation models to use - only including directly supported models
    foundation_models = [
        'anthropic.claude-3-sonnet-20240229-v1:0',
        'anthropic.claude-3-haiku-20240307-v1:0'
    ]

    # Handle recreation
    if args.recreate_agents.lower() == 'true':
        cleanup_agents(agents, agent_names)
        print("Cleaned up existing agents, creating new ones...")
        
        # Skip guardrail for now since the API has changed
        print("Skipping guardrail creation - please create the guardrail manually in the console if needed")
        
        # Get Lambda ARNs (we assume the Lambdas are already deployed)
        web_search_lambda_arn = get_lambda_arn("web_search", region, account_id)
        stock_data_lambda_arn = get_lambda_arn("stock_data_lookup", region, account_id)
        
        print(f"Using web search Lambda: {web_search_lambda_arn}")
        print(f"Using stock data Lambda: {stock_data_lambda_arn}")
        
        # Step 1: Create the news agent without action groups first
        news_description = "Market News Researcher"
        news_instructions = "Top researcher in financial markets and company announcements."
        
        news_agent_id, news_agent_alias_id, news_agent_arn = create_agent(
            agents, news_agent_name, news_description, news_instructions, 
            foundation_models, "DISABLED"
        )
        
        # Prepare the news agent
        agents.prepare(agent_name=news_agent_name)
        agents.wait_agent_status_update(agent_id=news_agent_id)
        
        # Create an alias for the news agent
        news_alias_id, news_alias_arn = agents.create_agent_alias(
            agent_id=news_agent_id, 
            alias_name="news-alias"
        )
        
        # Step 2: Create the stock data agent without action groups
        stock_data_description = "Financial Data Collector"
        stock_data_instructions = "Specialist in real-time financial data extraction."
        
        stock_data_agent_id, stock_data_alias_id, stock_data_agent_arn = create_agent(
            agents, stock_data_agent_name, stock_data_description, stock_data_instructions, 
            foundation_models, "DISABLED"
        )
        
        # Prepare the stock data agent
        agents.prepare(agent_name=stock_data_agent_name)
        agents.wait_agent_status_update(agent_id=stock_data_agent_id)
        
        # Create an alias for the stock data agent
        stock_data_alias_id, stock_data_alias_arn = agents.create_agent_alias(
            agent_id=stock_data_agent_id, 
            alias_name="stock-data-alias"
        )
        
        # Step 3: Create the analyst agent (no action groups needed)
        analyst_description = "Financial Analyst"
        analyst_instructions = (
            "Analyze stock trends and market news to generate insights. "
            "Experienced analyst providing strategic recommendations. "
            "You take as input the news summary and stock price summary."
        )
        
        analyst_agent_id, analyst_alias_id, analyst_agent_arn = create_agent(
            agents, analyst_agent_name, analyst_description, analyst_instructions, 
            foundation_models, "DISABLED"
        )
        
        # Prepare the analyst agent
        agents.prepare(agent_name=analyst_agent_name)
        agents.wait_agent_status_update(agent_id=analyst_agent_id)
        
        # Create an alias for the analyst agent
        analyst_alias_id, analyst_alias_arn = agents.create_agent_alias(
            agent_id=analyst_agent_id, 
            alias_name="analyst-alias"
        )
        
        # Step 4: Create the portfolio assistant (supervisor) agent
        portfolio_description = "Portfolio Assistant Agent"
        portfolio_instructions = (
            "Act as a seasoned expert at analyzing a potential stock investment for a given "
            "stock ticker. Do your research to understand how the stock price has been moving "
            "lately, as well as recent news on the stock. Give back a well written and "
            "carefully considered report with considerations for a potential investor. "
            "You use your analyst collaborator to perform the final analysis, and you give "
            "the news and stock data to the analyst as input. Use your collaborators in sequence, not in parallel."
        )
        
        portfolio_assistant_id, portfolio_assistant_alias_id, portfolio_assistant_arn = create_agent(
            agents, portfolio_assistant_name, portfolio_description, portfolio_instructions, 
            foundation_models, "SUPERVISOR"
        )
        
        # Step 5: Set up the collaboration hierarchy
        sub_agent_list = [
            {
                "sub_agent_alias_arn": news_alias_arn,
                "sub_agent_instruction": "Use this collaborator for finding news about specific stocks.",
                "sub_agent_association_name": news_agent_name,
                "relay_conversation_history": "DISABLED"
            },
            {
                "sub_agent_alias_arn": stock_data_alias_arn,
                "sub_agent_instruction": "Use this collaborator for finding price history for specific stocks.",
                "sub_agent_association_name": stock_data_agent_name,
                "relay_conversation_history": "DISABLED"
            },
            {
                "sub_agent_alias_arn": analyst_alias_arn,
                "sub_agent_instruction": "Use this collaborator for taking the raw research and writing a detailed report and investment considerations.",
                "sub_agent_association_name": analyst_agent_name,
                "relay_conversation_history": "DISABLED"
            }
        ]
        
        # Step 6: Associate sub-agents with the supervisor
        agents.associate_sub_agents(portfolio_assistant_id, sub_agent_list)
        agents.wait_agent_status_update(agent_id=portfolio_assistant_id)
        
        # Step 7: Finally, prepare the supervisor agent
        agents.prepare(agent_name=portfolio_assistant_name)
        agents.wait_agent_status_update(agent_id=portfolio_assistant_id)
        
        print(f"Portfolio Assistant ready! (ID: {portfolio_assistant_id})")
        print("Run with --recreate_agents false to start the interactive session")
    else:
        # Try to get existing agents
        portfolio_assistant_id = agents.get_agent_id_by_name(portfolio_assistant_name)
        if not portfolio_assistant_id:
            print("Portfolio assistant agent not found. Please run with --recreate_agents true first")
            sys.exit(1)
        portfolio_assistant_alias_id = "TSTALIASID"  # Default alias ID
        
        # Interactive session
        print(f"Using existing Portfolio Assistant (ID: {portfolio_assistant_id})")
        print("Type your prompt and hit Enter. Type 'exit' or 'quit' to stop.")
        print(f"The default ticker is {args.ticker}. Use --ticker to change it.")
        
        # First run automated analysis
        print(f"\nRunning automated analysis for ticker {args.ticker}...\n")
        
        # Create a prompt with the ticker
        prompt = f"Analyze the stock {args.ticker}. Look up recent news and stock price data, then provide a detailed analysis and investment considerations."
        
        # Invoke the agent
        print("Analyzing... (this may take a minute)")
        result = agents.invoke(
            input_text=prompt,
            agent_id=portfolio_assistant_id,
            agent_alias_id=portfolio_assistant_alias_id
        )
        print("\nAnalysis Results:\n")
        print(result)
        print("\n" + "-"*80 + "\n")
        
        # Start interactive session
        print("Now entering interactive mode. Ask questions about stocks or request analysis.")
        print("Type 'exit' or 'quit' to stop.")
        
        while True:
            try:
                prompt = input("\nYou: ")
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                sys.exit(0)

            if prompt.strip().lower() in {'exit', 'quit'}:
                print("Goodbye!")
                break

            # Invoke the agent
            result = agents.invoke(
                input_text=prompt,
                agent_id=portfolio_assistant_id,
                agent_alias_id=portfolio_assistant_alias_id
            )
            print(f"\nPortfolio Assistant: {result}")

if __name__ == '__main__':
    main() 