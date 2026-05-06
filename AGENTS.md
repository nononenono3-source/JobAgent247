# JobAgent247 AI Rules

## Core Philosophy
- Prioritize reliability over complexity
- Use a modular monolith architecture
- Keep everything in one repository and runtime
- Optimize for GitHub Actions free tier

## Architecture
- Avoid microservices
- Avoid RabbitMQ and Redis
- Use modular folders and services
- Keep orchestration centralized

## Workflow
- Explain plans before coding
- Break implementation into small phases
- Test after each major step
- Never modify unrelated files

## State Management
- Use JSON or SQLite
- Prevent duplicate job posting
- Maintain retry queues
- Save processing states

## Rendering
- Use reusable templates
- Support Instagram carousel slicing
- Handle Unicode safely
- Separate rendering from business logic

## Uploads
- Validate URLs before upload
- Retry failed uploads safely
- Prevent duplicate publishing
- Handle API rate limits

## Safety
- Never overwrite .env
- Never delete production files
- Ask before architecture changes
- Avoid dangerous terminal commands

## Performance
- Minimize API calls
- Avoid infinite loops
- Optimize for low compute usage