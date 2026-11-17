
'''
This demonstrates three important production concepts:
- Execution limits: Prevent excessive or infinite tool execution.
- Goal validation: Check whether the user's requirement was satisfied.
- Failure reporting: Distinguish an incomplete task from a successful outcome.
'''
MAX_SEARCHES = 2
searches = 0

BUDGET = 100

def search_trains():
    return {
        "transport": "train",
        "price": 135
    }

def search_buses():
    return {
        "transport": "bus",
        "price": 125
    }

tools = {
    "search_trains": search_trains,
    "search_buses": search_buses
}

print(f"Goal: Find transport under €{BUDGET}")

action = "search_trains"

while searches < MAX_SEARCHES:
    observation = tools[action]()
    searches += 1

    print("Tool result:", observation)

    if observation["price"] <= BUDGET:
        print("Valid option found!")
        break

    if searches >= MAX_SEARCHES:
        print("Search limit reached. No valid option found.")
        break

    action = input(
        "Choose next action (search_trains/search_buses): "
    ).strip()

    if action not in tools:
        print("Invalid action. Stopping.")
        break
