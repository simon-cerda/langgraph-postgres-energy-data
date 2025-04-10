from agent.state import State
from langchain_core.messages import HumanMessage, AIMessage
from agent.graph import graph  # your compiled graph

async def run_conversation(user_input, history=None):
    if history is None:
        history = []

    history.append(HumanMessage(content=user_input))
    state = State(messages=history)

    result = await graph.ainvoke(state)
    updated_messages = result["messages"]

    assistant_message = next(
        (msg.content for msg in reversed(updated_messages) if isinstance(msg, AIMessage)),
        "Hmm... I didn’t get that."
    )


    return assistant_message, updated_messages

if __name__ == "__main__":
    import asyncio

    history = []
    while True:
        user_input = input("You: ")
        response, history = asyncio.run(run_conversation(user_input, history))
        print("Bot:", response)