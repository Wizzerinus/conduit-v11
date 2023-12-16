## Conduit v11

### Description

This is a simple web application that is used for math class management.
It allows creating sheets (through a TeX template), extract problems from these sheets
and create mark tables for them.

Conduit is using FastAPI with a json-file-based database.

---

Conduit - простое web-приложение для управления уроками матанализа.
Оно позволяет создавать листы (через TeX шаблон), извлекать из них задачи
и создавать таблицы оценок для них.

Conduit использует FastAPI с базой данных на основе json файлов.

### Dev Installation

* Clone the repository
* Install the dependencies with pipenv or through requirements.txt (at least Python 3.10 is required)
* Create required secrets with `python -m pyconduit.setup generate-salts`
* If needed, copy `json-db-example` to `json-db`
* Create an administrator account with `python -m pyconduit.setup create-admin`
* Run the server with `uvicorn pyconduit.website.website:app --reload --reload-include *.yml --host 0.0.0.0 --workers 1`
