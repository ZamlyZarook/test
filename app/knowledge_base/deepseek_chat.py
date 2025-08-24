import os
import requests
import matplotlib
matplotlib.use('Agg')  # Set the backend to non-interactive Agg
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from flask import current_app
from ..models import KnowledgeBaseMaster

def generate_sql(prompt: str, kb_id: int, chat_history: list) -> str:
    """Generate SQL query from a natural language prompt using DeepSeek's API."""
    # Get API key from app config
    api_key = current_app.config.get('DEEPSEEK_API_KEY')
    if not api_key:
        return "Error: DeepSeek API key not configured"
    
    # Validate API key format
    if not api_key.startswith('sk-'):
        return "Error: DeepSeek API key appears to be invalid (should start with 'sk-')"

    # Get the knowledge base and its schema info
    kb = KnowledgeBaseMaster.query.get(kb_id)
    if not kb:
        return "Error: Knowledge base not found"
    
    schema_info = kb.description or ""
    if not schema_info.strip():
        return "Error: No schema information available in knowledge base. Please add a technical description to your knowledge base."

    print(f"Using API Key: {api_key[:10]}...")  # Log first 10 chars for debugging
    print(f"Schema info length: {len(schema_info)} characters")

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    HEADERS = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # Prepare messages including chat history
    messages = [
        {
            "role": "system",
            "content": f"""You are a SQL query generator for MySQL. Use ONLY the following schema:
            {schema_info}

            Generate a MySQL query that follows these rules:
            1. Always use meaningful table aliases (e.g., 'employees e', 'departments d')
            2. For aggregations, include proper GROUP BY clauses
            3. For charts, ensure the first column is the label and the second column is numeric
            4. Return only necessary columns, avoiding 'SELECT *'
            5. End the query with a semicolon
            6. Use proper JOIN syntax with ON conditions
            7. Include column aliases using AS for better readability
            8. Use LIMIT instead of TOP for row limiting
            9. Use MySQL-specific syntax (not SQL Server/T-SQL)

            Respond ONLY with the SQL query, without any explanation or markdown formatting."""
        }
    ]

    # Add chat history (last 5 messages to prevent context from getting too large)
    messages.extend([
        {"role": msg["role"], "content": msg["content"]} 
        for msg in chat_history[-5:]
    ])

    # Add current prompt
    messages.append({
        "role": "user",
        "content": prompt
    })

    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.1
    }

    try:
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        
        # Log the response for debugging
        print(f"DeepSeek API Response Status: {response.status_code}")
        print(f"DeepSeek API Response Headers: {response.headers}")
        print(f"DeepSeek API Response Content: {response.text}")
        
        # Check if the response is successful
        if response.status_code != 200:
            return f"Error: API returned status {response.status_code}: {response.text}"
        
        output = response.json()
        
        if "choices" in output and output["choices"]:
            sql = output["choices"][0]["message"]["content"].strip()
            sql = sql.replace("```sql", "").replace("```", "").strip()
            if not sql.endswith(';'):
                sql += ';'
            return sql
        else:
            print(f"DeepSeek API Response Structure: {output}")
            return f"Error: No SQL query generated. API response: {output}"

    except requests.exceptions.RequestException as e:
        return f"Error: API request failed - {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

def generate_chart(columns, data, chart_type, filename):
    """Generate chart based on chart_type and save as an image."""
    # Create the charts directory if it doesn't exist
    os.makedirs("static/charts", exist_ok=True)

    df = pd.DataFrame(data, columns=columns)
    chart_path = f"static/charts/{filename}.png"

    # Clear any existing plots
    plt.clf()

    # Create new figure
    plt.figure(figsize=(8, 6))

    try:
        if chart_type == "bar":
            sns.barplot(data=df, x=columns[0], y=columns[1])
        elif chart_type == "line":
            sns.lineplot(data=df, x=columns[0], y=columns[1])
        elif chart_type == "pie":
            df.set_index(columns[0])[columns[1]].plot.pie(autopct="%1.1f%%")

        plt.title(f"{chart_type.capitalize()} Chart")
        plt.tight_layout()  # Adjust layout to prevent label cutoff
        plt.savefig(chart_path)
        plt.close("all")  # Close all figures to free memory
        return chart_path

    except Exception as e:
        print(f"Error generating chart: {str(e)}")
        plt.close("all")  # Make sure to close figures even if there's an error
        return None
