import os
import json
from openai import OpenAI
from moviegraph.neo4j import get_db

# Connect to OpenAI
# It will automatically use the OPENAI_API_KEY environment variable.
client = OpenAI()

# Provide the schema of the database to the LLM so it knows what Cypher it can write.
SCHEMA_TEXT = """
Nodes:
- (m:Movie {id: String, title: String, year: Integer, rating: Float, description: String})
- (p:Person {name: String})
- (g:Genre {name: String})
- (u:User {username: String})

Relationships:
- (m)-[:HAS_GENRE]->(g)
- (m)-[:ACTED_BY]->(p)
- (m)-[:DIRECTED_BY]->(p)
- (m)-[:SIMILAR_TO]->(m2:Movie)
- (u)-[:WATCHED]->(m)
- (u)-[:WATCHLIST]->(m)
"""

def generate_cypher(user_query):
    """Ask OpenAI to convert natural language into a Cypher query."""
    prompt = f"""
You are an expert Neo4j Cypher developer for a Movie Recommendation Graph.
Here is the schema:
{SCHEMA_TEXT}

Generate a Cypher query to answer the user's question.
Rules:
1. ONLY return the raw Cypher query string. No markdown, no explanations, no `cypher` wrappers.
2. Limit the results to 5 using LIMIT 5.
3. Return m.title as title, m.id as id, and m.description as description for any movie matches.
4. If they ask for movies, make sure to RETURN title, id, description.
5. ALWAYS use case-insensitive matching for string comparisons (e.g. WHERE toLower(g.name) CONTAINS toLower('sci-fi') or WHERE g.name =~ '(?i)sci-fi'). Do NOT use exact case matching like {{name: 'Sci-fi'}} because the database case might differ.
6. If the user's input is just a greeting, a thank you, or general chit-chat that doesn't require querying the database, return the exact string "NONE".

User Question: {user_query}
    """
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    
    # Clean up response (sometimes models still output markdown despite instructions)
    cypher = response.choices[0].message.content.strip()
    if cypher.startswith("```cypher"):
        cypher = cypher[9:]
    if cypher.startswith("```"):
        cypher = cypher[3:]
    if cypher.endswith("```"):
        cypher = cypher[:-3]
        
    return cypher.strip()

def run_cypher(cypher_query):
    """Execute the cypher query against Neo4j."""
    db = get_db()
    try:
        results = db.run(cypher_query)
        # Convert records to a list of dicts for the LLM context
        return [dict(record) for record in results]
    except Exception as e:
        print(f"Cypher Execution Error: {e}")
        return []

def generate_response(user_query, cypher_query, db_results):
    """Ask OpenAI to formulate a friendly response based on the DB results."""
    prompt = f"""
You are a friendly AI Movie Assistant on a website called MovieGraph.
The user asked: "{user_query}"
We ran this Cypher query: {cypher_query}
The database returned these results: {json.dumps(db_results, default=str)}

Write a friendly, enthusiastic response answering their question based ONLY on the database results.
If the cypher query is "NONE", it means the user was just greeting you or chatting. In that case, just reply politely and ask how you can help them find a movie today.
If the database returned movies with an 'id' and 'title', you MUST format them as HTML links like this:
<a href="/movies/THE-ID" class="movie-card-inline"><strong>THE TITLE</strong><br>Brief description here...</a>

If the results are empty and it was an actual search, apologize and say you couldn't find anything matching that in the database.
Keep it conversational and short.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    
    return response.choices[0].message.content.strip()

def process_chat(user_query):
    """Main pipeline for the RAG chatbot."""
    try:
        # 1. Generate Cypher
        cypher = generate_cypher(user_query)
        print(f"Generated Cypher: {cypher}")
        
        # 2. Query DB
        if cypher.strip().upper() == "NONE":
            results = []
        else:
            results = run_cypher(cypher)
        print(f"DB Results: {results}")
        
        # 3. Generate Final HTML Answer
        final_answer = generate_response(user_query, cypher, results)
        return final_answer
    except Exception as e:
        print(f"Chat Pipeline Error: {e}")
        return "I'm sorry, I encountered an error while trying to think about that."
