from fastapi.testclient import TestClient
from fastapi import HTTPException
from main import app
from repositories.faq_repository import FAQRepository
from models.faq_models import FAQEntry, FAQUpdate
from azure.core.exceptions import ResourceNotFoundError


class MockFAQRepository:
    def get_faqs_by_category(self, category=None):
        faqs = [
            {
                "question": "Mocked Question 1",
                "answer": "Mocked Answer 1",
                "category": "test",
                "id": "1",
            },
            {
                "question": "Mocked Question 2",
                "answer": "Mocked Answer 2",
                "category": "notTest",
                "id": "2",
            },
        ]
        if category:
            return [faq for faq in faqs if faq["category"] == category]
        return faqs

    def create_faq_entry(self, faq: FAQEntry):
        # Generate the UUID for the RowKey
        row_key = "ea6c740e-9bdc-42f1-b1a6-5bdece390c93"

        faq_dict = faq.dict()

        faq_entity = {
            **{"PartitionKey": faq.category},
            **{k.capitalize(): v for k, v in faq_dict.items()},
        }

        return row_key, faq_entity

    def get_faq_by_id(self, category: str, faq_id: str):
        if faq_id == "1":
            return {
                "question": "Mocked Question 1",
                "answer": "Mocked Answer 1",
                "category": "test",
                "id": "1",
            }
        raise HTTPException(status_code=404, detail="FAQ not found")

    def update_faq(self, category: str, faq_id: str, faq: FAQUpdate):
        return {**faq.dict(), "id": faq_id, "category": category}

    def delete_faq(self, category: str, faq_id: str):
        if not (
            (faq_id == "1" and category == "test")
            or (faq_id == "2" and category == "notTest")
        ):
            raise ResourceNotFoundError(
                f"FAQ entry with ID {faq_id} not found in category {category}."
            )

        return {
            "success": True,
            "message": f"FAQ with ID '{faq_id}' successfully deleted from category '{category}'.",
        }

    def increment_clicks(self, category: str, faq_id: str):
        if faq_id != "1" or category != "test":
            raise HTTPException(
                status_code=404, detail=f"FAQ entry with ID {faq_id} not found."
            )
        return 1


# Override the actual dependency with the MockFAQRepository
app.dependency_overrides[FAQRepository] = lambda: MockFAQRepository()

client = TestClient(app)


# Test for POST /faqs
def test_create_faq():
    faq_data = {
        "question": "New Question",
        "answer": "New Answer",
        "category": "test",
    }
    response = client.post("/faqs", json=faq_data)
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "FAQ entry created successfully"
    assert data["data"]["question"] == "New Question"
    assert data["data"]["answer"] == "New Answer"


def test_create_faq_missing_fields():
    incomplete_faq_data = {
        "question": "Incomplete Question"
    }  # Missing 'answer' and 'category'
    response = client.post("/faqs", json=incomplete_faq_data)
    assert response.status_code == 422


def test_create_faq_input_too_short():
    incomplete_faq_data = {
        "question": "In",
        "answer": "com",
        "category": "plete",
    }  # Missing 'answer' and 'category'
    response = client.post("/faqs", json=incomplete_faq_data)
    assert response.status_code == 422


# Test for GET /faqs
def test_get_faqs():
    response = client.get("/faqs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2  # Expecting 2 FAQs
    assert data[0]["question"] == "Mocked Question 1"
    assert data[1]["question"] == "Mocked Question 2"


# Test for GET /faqs with a category filter
def test_get_faqs_by_category():
    response = client.get("/faqs?category=test")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1  # Only one FAQ for the 'test' category
    assert data[0]["question"] == "Mocked Question 1"


# Test for GET /faqs/{category}/{faq_id}
def test_get_faq_by_id():
    response = client.get("/faqs/test/1")
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Mocked Question 1"
    assert data["answer"] == "Mocked Answer 1"


def test_get_faq_by_id_not_found():
    response = client.get("/faqs/test/999")
    assert response.status_code == 404


# Test for PUT /faqs/{category}/{faq_id}
def test_update_faq():
    updated_faq = {"question": "Updated Question", "answer": "Updated Answer"}
    response = client.put("/faqs/test/1", json=updated_faq)
    assert response.status_code == 200
    data = response.json()
    assert data["question"] == "Updated Question"
    assert data["answer"] == "Updated Answer"


# Test for DELETE /faqs/{category}/{faq_id}
def test_delete_faq():
    response = client.delete("/faqs/test/1")
    assert response.status_code == 200


def test_delete_nonexistent_faq():
    response = client.delete("/faqs/test/999")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "FAQ entry with ID 999 not found in category test."


# Test for POST /faqs/{category}/{faq_id}/click
def test_increment_clicks():
    response = client.post("/faqs/test/1/click")
    assert response.status_code == 200
    data = response.json()
    assert data["detail"] == "Clicks incremented successfully."
    assert data["new_clicks"] == 1


def test_increment_clicks_nonexistent():
    response = client.post("/faqs/test/999/click")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "FAQ entry with ID 999 not found."


# Test for GET /faqs with category filter returning no data
def test_get_faqs_by_category_no_data():
    response = client.get("/faqs?category=unknown")
    assert response.status_code == 404
    data = response.json()
    assert len(data) == 1  # No FAQs for the 'unknown' category
    assert data["detail"] == "No FAQs found for the specified category."


# Test for POST /faqs with invalid data (missing required fields)
def test_create_faq_invalid_data():
    invalid_faq_data = {"question": "Incomplete FAQ"}
    response = client.post("/faqs", json=invalid_faq_data)
    assert response.status_code == 422  # Unprocessable Entity


# Test for PUT /faqs/{category}/{faq_id} with invalid data (empty fields)
def test_update_faq_empty_fields():
    updated_faq = {"question": "", "answer": ""}
    response = client.put("/faqs/test/1", json=updated_faq)
    assert response.status_code == 422


# Test for PUT /faqs/{category}/{faq_id} with invalid data (empty fields)
def test_update_faq_no_fields():
    updated_faq = {}
    response = client.put("/faqs/test/1", json=updated_faq)
    assert response.status_code == 400
