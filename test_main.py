from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app, table_client  # assuming your app is in `main.py`

client = TestClient(app)


# Prepare the mock database

# Mock data for the tests
mock_faqs = [
    {"Question": "What is FastAPI?", "Answer": "FastAPI is a web framework.", "Category": "General", "PartitionKey": "General", "RowKey": "1"},
    {"Question": "How do I install FastAPI?", "Answer": "Use pip.", "Category": "Installation", "PartitionKey": "Installation", "RowKey": "2"}
]

def mock_query_entities(query_filter):
    # This is the mock function that simulates querying the table
    if query_filter == "PartitionKey eq 'General'":
        return [mock_faqs[0]]  # Return only the first FAQ if filtering by 'General'
    elif query_filter == "PartitionKey eq 'Installation'":
        return [mock_faqs[1]]  # Return only the second FAQ if filtering by 'Installation'
    elif query_filter is not None and query_filter != "PartitionKey eq 'General'" and query_filter != "PartitionKey eq 'Installation'" and query_filter != "":
        return []
    else:
        return mock_faqs  # Return all FAQs if no filter or invalid filter is used

# Replace the real table_client with the mock
table_client.query_entities = MagicMock(side_effect=mock_query_entities)


# Run the GET /faqs endpoint

# Test 1: Test GET /faqs with no category in header (should return all FAQs)
def test_get_all_faqs():
    response = client.get("/faqs", headers={"accept": "application/json"})
    
    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 2  # We have two FAQs in the mock data
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[1]["question"] == "How do I install FastAPI?"

# Test 2: Test GET /faqs with category in header (should return FAQs filtered by category)
def test_get_faqs_by_category():
    response = client.get("/faqs", headers={"accept": "application/json", "category": "General"})
    
    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 1  # Only one FAQ in the "General" category
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[0]["category"] == "General"

# Test 3: Test GET /faqs with a non-existing category (should return empty list)
def test_get_faqs_by_non_existing_category():
    response = client.get("/faqs", headers={"accept": "application/json", "category": "adawddwwefwef"})
    
    assert response.status_code == 404
    assert response.json() == {"detail": "No FAQs found."}

# Test 4: Test GET /faqs with internal server error (mock an exception in query_entities)
def test_get_faqs_internal_error():
    # Simulate an exception by mocking query_entities to raise an error
    table_client.query_entities = MagicMock(side_effect=Exception("Database connection error"))
    
    response = client.get("/faqs", headers={"accept": "application/json"})
    
    assert response.status_code == 500
    assert response.json() == {"detail": "Database connection error"}