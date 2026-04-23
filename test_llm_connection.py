#!/usr/bin/env python3
"""
test_llm_connection.py — Test LLM API connectivity
=====================================================
Run this to diagnose API connection issues:
  python test_llm_connection.py
"""

import os
import sys
from pathlib import Path

# Load .env if it exists
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

def test_provider(provider: str, api_key: str) -> bool:
    """Test a specific provider's API connectivity."""
    from agent.llm_client import LLMClient
    
    print(f"\n{'='*60}")
    print(f"Testing {provider.upper()} API")
    print(f"{'='*60}")
    
    if not api_key:
        print(f"❌ No API key found for {provider.upper()}")
        return False
    
    print(f"✓ API Key found (length: {len(api_key)} chars)")
    
    try:
        # Create client
        client = LLMClient(provider=provider)
        print(f"✓ LLMClient initialized")
        print(f"  Provider: {client.provider.upper()}")
        print(f"  Model: {client.model}")
        print(f"  Endpoint: {client.api_url}")
        
        # Test with simple prompt
        print(f"\nTesting with simple prompt...")
        response, tokens = client.call(
            "Say 'Hello' and nothing else.",
            max_tokens=50
        )
        print(f"✓ API call successful!")
        print(f"  Response: {response[:100]}")
        print(f"  Tokens used: {tokens}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)[:500]}")
        return False


def main():
    print("\n🔍 LLM API Connectivity Test\n")
    
    # Get available providers from environment
    providers_to_test = {
        "gemini": os.environ.get("GEMINI_API_KEY", ""),
        "groq": os.environ.get("GROQ_API_KEY", ""),
        "grok": os.environ.get("GROK_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
    }
    
    # Show current provider
    current_provider = os.environ.get("LLM_PROVIDER", "not set").lower()
    print(f"Current LLM_PROVIDER: {current_provider}")
    print(f"\nAvailable API keys:")
    for prov, key in providers_to_test.items():
        status = "✓ Present" if key else "✗ Missing"
        print(f"  {prov.upper():10} {status}")
    
    # Test current provider first
    if current_provider in providers_to_test:
        api_key = providers_to_test[current_provider]
        if api_key:
            test_provider(current_provider, api_key)
        else:
            print(f"\n❌ Current provider {current_provider.upper()} has no API key!")
            print(f"   Set it with: $env:{current_provider.upper()}_API_KEY=\"your_key\"")
    
    # Test other providers if user wants
    print(f"\n{'='*60}")
    print("To test other providers, set their API keys:")
    print("  $env:GEMINI_API_KEY=\"...\";    python test_llm_connection.py")
    print("  $env:GROQ_API_KEY=\"...\";      python test_llm_connection.py")
    print("  $env:GROK_API_KEY=\"...\";      python test_llm_connection.py")
    print("  $env:ANTHROPIC_API_KEY=\"...\"; python test_llm_connection.py")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
