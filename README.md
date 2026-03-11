# Korra
K.O.R.R.A = "Knowledge-Oriented Responsive Resource Assistant"


# Korra Voice Pipeline

Korra is a local voice assistant pipeline designed to run fully offline with low latency.  
The goal of this project is to build a fast, private voice interface that integrates with other services such as OpenClaw and home automation systems.

This repository currently contains an early prototype of the voice pipeline.

---

## Current Features

- Wake word detection using **Porcupine**
- Speech-to-text using **Faster-Whisper**
- Text-to-speech using **Piper**
- Local microphone input and speaker output
- Designed for **low latency local processing**

---

## Architecture (Current)

Wake Word → Record Audio → Speech-to-Text → Response → Text-to-Speech → Speaker Output

Components:

- **Wake Word:** Picovoice Porcupine  
- **STT:** Faster Whisper  
- **TTS:** Piper  
- **Language Runtime:** Python

---

## Project Structure
Korra/
│
├── scripts/
│   └── test_pipeline.py
│
├── tts/
│
├── .gitignore
├── LICENSE.txt
└── README.md

---

## Goals

This project will evolve into a full voice interface capable of:

- Integrating with **OpenClaw**
- Running entirely **offline**
- Providing **low-latency voice interaction**
- Controlling infrastructure and services
- Supporting additional plugins and integrations

---

## Hardware Environment

Currently tested on:

- Linux server (Proxmox node)
- Local microphone and speaker devices
- Python virtual environment

---

## Status

Early prototype
The pipeline is functional but still being optimized for latency and modular design.

---

## Future Improvements

- Streaming STT for faster responses
- Persistent audio pipeline
- OpenClaw integration
- Modular command handlers
- Hardware abstraction for audio devices

---

## License

See `LICENSE.txt`.
