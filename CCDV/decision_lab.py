
# Domain 1 - Agent Architecture Lab
# Human-guided simulation of a decision loop

BUDGET = 100

def search_trains():
    return {
        "transport": "train",
        "price": 135
    }

def search_buses():
    return {
        "transport": "bus",
        "price": 65
    }

tools = {
    "search_trains": search_trains,
    "search_buses": search_buses
}

print(f"Goal: Find transport under €{BUDGET}")

action = "search_trains"

while True:
    observation = tools[action]()
    print("\nTool result:", observation)

    if observation["price"] <= BUDGET:
        print("Valid option found!")
        break

    print("Current option exceeds budget.")
    print("Available next actions: search_buses, finish")

    next_action = input("Choose next action: ").strip()

    if next_action == "finish":
        print("Stopped without finding a valid option.")
        break

    if next_action not in tools:
        print("Invalid action. Try again.")
        continue

    action = next_action
