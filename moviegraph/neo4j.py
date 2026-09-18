import os
from neo4j import GraphDatabase

# In a real deployment, these come from the environment.
URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

driver = None

def get_driver():
    global driver
    if driver is None:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
    return driver

def get_db():
    return get_driver().session()
