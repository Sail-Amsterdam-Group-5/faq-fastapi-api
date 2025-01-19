from fastapi.testclient import TestClient
from fastapi import HTTPException
from main import app
from repositories.faq_repository import FAQRepository
from models.faq_models import FAQEntry, FAQUpdate


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
        return {"message": "FAQ entry created successfully", "data": faq.dict()}

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
        return {"message": "FAQ deleted successfully"}

    def increment_clicks(self, category: str, faq_id: str):
        return {"detail": "Clicks incremented successfully", "new_clicks": 1}


# Override the actual dependency with the MockFAQRepository
app.dependency_overrides[FAQRepository] = lambda: MockFAQRepository()

client = TestClient(app)


# Test for POST /faqs
def test_create_faq():
    faq_data = {"question": "New Question", "answer": "New Answer", "category": "test"}
    response = client.post("/faqs", json=faq_data)
    assert response.status_code == 201
    data = response.json()
    assert data["message"] == "FAQ entry created successfully"
    assert data["data"]["question"] == "New Question"
    assert data["data"]["answer"] == "New Answer"


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
    assert response.status_code == 204


# Test for POST /faqs/{category}/{faq_id}/click
def test_increment_clicks():
    response = client.post("/faqs/test/1/click")
    assert response.status_code == 200
    data = response.json()
    assert data["detail"] == "Clicks incremented successfully"
    assert data["new_clicks"] == 1


# Test for GET /faqs with category filter returning no data
def test_get_faqs_by_category_no_data():
    response = client.get("/faqs?category=unknown")
    assert response.status_code == 404
    data = response.json()
    assert len(data) == 1  # No FAQs for the 'unknown' category
    assert data["detail"] == "No FAQs found."


# Test for POST /faqs with invalid data (missing required fields)
def test_create_faq_invalid_data():
    invalid_faq_data = {"question": "Incomplete FAQ"}
    response = client.post("/faqs", json=invalid_faq_data)
    assert response.status_code == 422  # Unprocessable Entity


# Test for PUT /faqs/{category}/{faq_id} with invalid data
# def test_update_faq_invalid_data():
#     invalid_faq_data = {
#         "question": "Is this a test aaaaaaaaaaa?"
#     }  # Missing 'answer' and 'category'
#     response = client.put("/faqs/test/1", json=invalid_faq_data)

#     # Ensure the response status code is 422 for validation error
#     assert (
#         response.status_code == 422
#     )  # Validation error status code (Unprocessable Entity)

#     # Define the expected response structure
#     expected_response = {
#         "detail": [
#             {
#                 "type": "missing",
#                 "loc": ["body", "answer"],
#                 "msg": "Field required",
#                 "input": {"question": "Is this a test aaaaaaaaaaa?"},
#             },
#             {
#                 "type": "missing",
#                 "loc": ["body", "category"],
#                 "msg": "Field required",
#                 "input": {"question": "Is this a test aaaaaaaaaaa?"},
#             },
#         ]
#     }

#     # Assert the actual response matches the expected response
#     assert response.json() == expected_response
