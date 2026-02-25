#!/usr/bin/env bash

echo "Updating packages..."

apt-get update

echo "Installing Tesseract OCR..."

apt-get install -y tesseract-ocr

echo "Installing Poppler (PDF → Image conversion)..."

apt-get install -y poppler-utils

echo "Build completed successfully"