# Neha AI — Project Status

## 1. Project Goal
Build a personal AI assistant with a dedicated Android app, natural conversations, persistent memory, voice interaction, and supported phone controls.

## 2. Developer Environment
- Device: Android phone
- Development: Termux
- Language: Python
- Mobile app: Expo / React Native
- Computer available: No
- Preference: Free tools and services wherever practical

## 3. Repository
GitHub:
https://github.com/sumankadam003-art/My--ai--assistant-

Project directory:
~/My--ai--assistant-/

## 4. Important Files
- src/main.py — Main Python assistant
- src/actions.py — Phone actions
- src/voice.py — Voice functionality
- src/memory.py — Memory management
- src/memory_brain.py — Memory-related logic
- src/memory_selector.py — Memory selection
- src/groq_brain.py — Groq integration
- src/gemini_brain.py — Gemini integration
- src/neha_gateway.py — AI gateway
- src/app_api.py — API server for the mobile app
- src/chat_history.py — Chat history functionality
- src/intent_interpreter.py — Intent interpretation
- src/web_search.py — Web search
- neha-mobile/src/app/index.tsx — Mobile interface

Inspect the current code before modifying any file.

## 5. Features Previously Tested
- Groq-backed AI conversations
- Expo interface connected to the Python backend
- API health endpoint at /health
- Chat endpoint at /chat
- Voice input and text-to-speech
- Local memory functionality
- Battery status
- Volume controls
- Camera launch
- Opening supported apps
- Opening supported Android settings

Some features may have limitations depending on Android and Termux permissions. Retest when necessary.

## 6. API Information
Previously tested local endpoint:
http://127.0.0.1:8765

Health check:
GET /health

Chat:
POST /chat

The API and Expo servers were stopped safely at the last checkpoint.

## 7. Cloud Memory Plan
Supabase Free is the planned primary cloud database.
Setup is not yet confirmed complete.

Planned tasks:
1. Create the Supabase project.
2. Design the chat-history and memory tables.
3. Configure secure access controls.
4. Connect Supabase through the Python backend.
5. Test saving and retrieving conversations.
6. Explore Google Drive as a secondary backup.

Never put service-role keys or database passwords in the mobile app or GitHub.

## 8. Development Priorities
1. Set up Supabase.
2. Add secure cloud chat history.
3. Add persistent long-term memory.
4. Implement reliable backup and recovery.
5. Improve voice interaction.
6. Expand supported phone controls.
7. Improve app navigation and modules.
8. Build and test an installable Android APK.

## 9. Safety and Security Rules
- Never expose API keys, passwords, tokens, or private environment files.
- Keep secrets in the appropriate local environment configuration.
- Use database access controls and authentication.
- Ask permission before sensitive actions.
- Require additional secure confirmation for critical or irreversible actions.
- Explain consequences before performing critical actions.
- Back up important files before code modifications.
- Do not overwrite working features unnecessarily.
- Verify changes and tests before claiming success.

## 10. Instructions for Future ChatGPT Sessions
The developer works entirely on an Android phone using Termux and is not an experienced programmer.

Provide one manageable step at a time.
Explain commands simply.
Inspect existing code before modifying it.
Prefer free services and tools.
Include a short explanation of what each code change adds to Neha.
Preserve existing working functionality.
Ask for command output or screenshots when verification is needed.

At the beginning of a new session:
1. Read this file.
2. Inspect the repository and current Git status.
3. Confirm what is actually implemented and tested.
4. Continue from the current state without rebuilding everything.

## 11. Updating This File
Update this file whenever a major feature is completed, a technical decision changes, or an important problem is discovered.

Do not claim automatic updates unless an update mechanism has actually been implemented and tested.

## 12. Current Checkpoint
- Project files exist in the repository.
- Git ignore rules have been updated.
- Some Python backup files are excluded.
- Supabase setup is pending.
- Cloud persistence is not yet confirmed implemented.
- PROJECT_STATUS.md is being created as the development reference.
