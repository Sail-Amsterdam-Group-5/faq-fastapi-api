from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app, table_client
from azure.core.exceptions import ResourceNotFoundError

client = TestClient(app)

# Mock data for the tests
mock_faqs = [
    {
        "Question": "What is FastAPI?",
        "Answer": "FastAPI is a web framework.",
        "Category": "General",
        "PartitionKey": "General",
        "RowKey": "1",
        "Clicks": 10,
    },
    {
        "Question": "How do I install FastAPI?",
        "Answer": "Use pip.",
        "Category": "Installation",
        "PartitionKey": "Installation",
        "RowKey": "2",
        "Clicks": 5,
    },
]


def mock_query_entities(query_filter):
    if query_filter == "PartitionKey eq 'General'":
        return [mock_faqs[0]]  # Return only the first FAQ for 'General'
    elif query_filter == "PartitionKey eq 'Installation'":
        return [mock_faqs[1]]  # Return only the second FAQ for 'Installation'
    elif query_filter:
        return []  # Return an empty list for unknown filters
    else:
        return mock_faqs  # Return all FAQs when no filter is applied


# Mock the behavior of table_client for querying
table_client.query_entities = MagicMock(side_effect=mock_query_entities)


# Test GET /faqs without category header (should return all FAQs)
def test_get_all_faqs():
    response = client.get("/faqs", headers={"accept": "application/json"})

    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 2
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[1]["question"] == "How do I install FastAPI?"


# Test GET /faqs with category header (should return filtered FAQs)
def test_get_faqs_by_category():
    response = client.get(
        "/faqs", headers={"accept": "application/json", "category": "General"}
    )

    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 1
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[0]["category"] == "General"


# Test GET /faqs with a non-existing category (should return 404)
def test_get_faqs_by_non_existing_category():
    response = client.get(
        "/faqs", headers={"accept": "application/json", "category": "NonExistent"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "No FAQs found."}


# Test GET /faqs with simulated internal server error
def test_get_faqs_internal_error():
    table_client.query_entities = MagicMock(
        side_effect=Exception("Database connection error")
    )

    response = client.get("/faqs", headers={"accept": "application/json"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Database connection error"}


# Test GET /faqs/{category}/{faq_id} for a specific FAQ
def test_get_faq_by_id():
    table_client.get_entity = MagicMock(return_value=mock_faqs[0])

    response = client.get("/faqs/General/1", headers={"accept": "application/json"})

    assert response.status_code == 200
    faq = response.json()
    assert faq["question"] == "What is FastAPI?"
    assert faq["category"] == "General"


# Test GET /faqs/{category}/{faq_id} for non-existing FAQ
def test_get_faq_by_non_existing_id():
    table_client.get_entity = MagicMock(side_effect=ResourceNotFoundError)

    response = client.get("/faqs/General/99", headers={"accept": "application/json"})

    assert response.status_code == 404
    assert response.json() == {"detail": "FAQ not found."}


# Test POST /faqs/{category}/{faq_id}/click to increment clicks
def test_increment_clicks():
    mock_entity = mock_faqs[0].copy()
    mock_entity["Clicks"] = 11
    table_client.get_entity = MagicMock(return_value=mock_faqs[0])
    table_client.update_entity = MagicMock()

    response = client.post(
        "/faqs/General/1/click", headers={"accept": "application/json"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "detail": "Clicks incremented successfully.",
        "new_clicks": 11,
    }


# Test DELETE /faqs/{category}/{faq_id}
def test_delete_faq():
    table_client.delete_entity = MagicMock()

    response = client.delete("/faqs/General/1", headers={"accept": "application/json"})

    assert response.status_code == 204


# Test PUT /faqs/{category}/{faq_id} to update an FAQ
def test_update_faq():
    mock_entity = mock_faqs[0].copy()
    mock_entity["Question"] = "Updated Question"
    table_client.get_entity = MagicMock(return_value=mock_faqs[0])
    table_client.update_entity = MagicMock()

    response = client.put(
        "/faqs/General/1",
        headers={"accept": "application/json"},
        json={"question": "Updated Question"},
    )

    assert response.status_code == 200
    faq = response.json()
    assert faq["question"] == "Updated Question"
    assert faq["category"] == "General"

    # Test
