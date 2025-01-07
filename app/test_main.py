from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from azure.core.exceptions import ResourceNotFoundError
from main import app

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
    """Mock function to simulate Azure Table Storage query behavior."""
    if query_filter == "PartitionKey eq 'General'":
        return [mock_faqs[0]]
    elif query_filter == "PartitionKey eq 'Installation'":
        return [mock_faqs[1]]
    elif query_filter:
        return []
    return mock_faqs


@patch("main.table_client")
def test_insert_faq(mock_table_client):
    # Mock insert_entity to simulate successful insertion
    mock_table_client.create_entity = MagicMock()

    new_faq = {
        "question": "What is Python?",
        "answer": "Python is a programming language.",
        "category": "Programming",
        "clicks": 0,
    }

    response = client.post(
        "/faqs",
        headers={"accept": "application/json", "X-User-Roles": "admin"},
        json=new_faq,
    )

    # Check for successful creation
    assert response.status_code == 201
    faq = response.json()
    assert faq["data"]["question"] == new_faq["question"]
    assert faq["data"]["answer"] == new_faq["answer"]
    assert faq["data"]["category"] == new_faq["category"]


@patch("main.table_client")
def test_insert_faq_with_invalid_role(mock_table_client):
    # Mock insert_entity to simulate a role issue
    mock_table_client.create_entity = MagicMock()

    new_faq = {
        "question": "What is Python?",
        "answer": "Python is a programming language.",
        "category": "Programming",
        "clicks": 0,
    }

    response = client.post(
        "/faqs",
        headers={"accept": "application/json", "X-User-Roles": "volunteer"},
        json=new_faq,
    )

    # Check for forbidden access
    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have the necessary permissions to perform this action."
    }


# Patching table_client for all tests
@patch("main.table_client")
def test_get_all_faqs(mock_table_client):
    mock_table_client.query_entities = MagicMock(side_effect=mock_query_entities)

    response = client.get("/faqs", headers={"accept": "application/json"})

    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 2
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[1]["question"] == "How do I install FastAPI?"


@patch("main.table_client")
def test_get_faqs_by_category(mock_table_client):
    mock_table_client.query_entities = MagicMock(side_effect=mock_query_entities)

    response = client.get(
        "/faqs", headers={"accept": "application/json", "Category": "General"}
    )

    assert response.status_code == 200
    faqs = response.json()
    assert len(faqs) == 1
    assert faqs[0]["question"] == "What is FastAPI?"
    assert faqs[0]["category"] == "General"


@patch("main.table_client")
def test_get_faqs_by_non_existing_category(mock_table_client):
    mock_table_client.query_entities = MagicMock(side_effect=mock_query_entities)

    response = client.get(
        "/faqs", headers={"accept": "application/json", "category": "NonExistent"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "No FAQs found."}


@patch("main.table_client")
def test_get_faqs_internal_error(mock_table_client):
    mock_table_client.query_entities = MagicMock(
        side_effect=Exception("Database error")
    )

    response = client.get("/faqs", headers={"accept": "application/json"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Database error"}


@patch("main.table_client")
def test_get_faq_by_id(mock_table_client):
    mock_table_client.get_entity = MagicMock(return_value=mock_faqs[0])

    response = client.get("/faqs/General/1", headers={"accept": "application/json"})

    assert response.status_code == 200
    faq = response.json()
    assert faq["question"] == "What is FastAPI?"
    assert faq["category"] == "General"


@patch("main.table_client")
def test_get_faq_by_non_existing_id(mock_table_client):
    mock_table_client.get_entity = MagicMock(side_effect=ResourceNotFoundError)

    response = client.get("/faqs/General/99", headers={"accept": "application/json"})

    assert response.status_code == 404
    assert response.json() == {"detail": "FAQ not found."}


@patch("main.table_client")
def test_increment_clicks(mock_table_client):
    mock_table_client.get_entity = MagicMock(return_value=mock_faqs[0])
    mock_table_client.update_entity = MagicMock()

    response = client.post(
        "/faqs/General/1/click", headers={"accept": "application/json"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "detail": "Clicks incremented successfully.",
        "new_clicks": 11,
    }


@patch("main.table_client")
def test_delete_faq(mock_table_client):
    # Mock delete_entity to simulate successful deletion
    mock_table_client.delete_entity = MagicMock()

    response = client.delete(
        "/faqs/general/1",
        headers={"accept": "application/json", "X-User-Roles": "admin"},
    )

    # Check for status code 204
    assert response.status_code == 204
    # Ensure the response body is empty
    assert response.content == b""


@patch("main.table_client")
def test_delete_faq_with_invalid_role(mock_table_client):
    # Mock delete_entity to simulate successful deletion
    mock_table_client.delete_entity = MagicMock()

    response = client.delete(
        "/faqs/general/1",
        headers={"accept": "application/json", "X-User-Roles": "volunteer"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have the necessary permissions to perform this action."
    }


@patch("main.table_client")
def test_update_faq(mock_table_client):
    mock_entity = mock_faqs[0].copy()
    mock_entity["question"] = "Updated Question"
    mock_table_client.get_entity = MagicMock(return_value=mock_faqs[0])
    mock_table_client.update_entity = MagicMock()

    response = client.put(
        "/faqs/general/1",
        headers={"accept": "application/json", "X-User-Roles": "admin"},
        json={"question": "Updated Question"},
    )

    assert response.status_code == 200
    faq = response.json()
    assert faq["question"] == "Updated Question"
    assert faq["category"] == "General"


@patch("main.table_client")
def test_update_faq_invalid_role(mock_table_client):
    mock_entity = mock_faqs[0].copy()
    mock_entity["question"] = "Updated Question"
    mock_table_client.get_entity = MagicMock(return_value=mock_faqs[0])
    mock_table_client.update_entity = MagicMock()

    response = client.put(
        "/faqs/general/1",
        headers={"accept": "application/json", "X-User-Roles": "volunteer"},
        json={"question": "Updated Question"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "You do not have the necessary permissions to perform this action."
    }
