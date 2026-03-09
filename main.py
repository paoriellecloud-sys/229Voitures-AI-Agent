from fastapi import FastAPI
from modules.auto.logic import recommend_vehicle
from database import create_all_tables
from modules.agent_chat import auto_chat


# ==============================
# INITIALISATION DATABASE
# ==============================

create_all_tables()


# ==============================
# FASTAPI APPLICATION
# ==============================

app = FastAPI()


@app.post("/agent/chat")
def chat_agent(message: dict):

    user_message = message["message"]

    response = auto_chat(user_message)

    return {"response": response}


# ==============================
# CONSOLE APPLICATION
# ==============================

def show_menu():
    print("\n=== 229Voitures AI Agent ===")
    print("1. Get vehicle recommendation")
    print("2. Exit")


def main():
    while True:
        show_menu()
        choice = input("Select an option: ")

        if choice == "1":
            recommend_vehicle()

        elif choice == "2":
            print("Exiting 229Voitures Agent...")
            break

        else:
            print("Invalid option. Please try again.")


if __name__ == "__main__":
    main()