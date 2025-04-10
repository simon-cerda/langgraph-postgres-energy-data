import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from chat import run_conversation  # async function
from langchain_core.messages.base import BaseMessage
st.set_page_config(page_title="LangGraph Chatbot", page_icon="🤖")

st.title("🤖 LangGraph Chatbot")

# Session state to keep conversation history
if "history" not in st.session_state:
    st.session_state.history: list[BaseMessage] = []

# Input from user
user_input = st.chat_input("Say something...")

# Display chat history
for msg in st.session_state.history:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.markdown(msg.content)

# When user sends input
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run the async chatbot function and display output
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response, updated_history = asyncio.run(
                run_conversation(user_input, st.session_state.history)
            )
            st.markdown(response)

    # Update session state
    st.session_state.history = updated_history
