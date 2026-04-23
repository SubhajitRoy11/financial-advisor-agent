"""
test_key.py — Quick API key tester
Run this BEFORE main.py to confirm your key works:
  python test_key.py
"""
import os, sys
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from agent.llm_client import LLMClient

print(f"\nTesting your API key...")
print(f"Provider : {os.environ.get('LLM_PROVIDER', 'gemini')}")
print(f"Model    : {os.environ.get('LLM_MODEL', 'default')}")
print()

try:
    client = LLMClient()
    # Tiny test prompt — uses almost no quota
    response, tokens = client.call("Say only the word: WORKING", max_tokens=10)
    print(f"✅ API key works! Response: '{response.strip()}' ({tokens} tokens)")
    print(f"\nYou're good to run:")
    print(f"  python main.py --portfolio PORTFOLIO_002 --no-llm-eval")
except Exception as e:
    provider = os.environ.get('LLM_PROVIDER', 'gemini').lower()
    print(f"❌ Failed: {e}")
    print(f"\nThings to check:")
    if provider == 'grok':
        print(f"  1. Did you set $env:GROK_API_KEY in this PowerShell window?")
        print(f"  2. Get a free key from https://console.x.ai")
    elif provider == 'groq':
        print(f"  1. Did you set $env:GROQ_API_KEY in this PowerShell window?")
        print(f"  2. Get a free key from https://console.groq.com")
    elif provider == 'anthropic':
        print(f"  1. Did you set $env:ANTHROPIC_API_KEY in this PowerShell window?")
        print(f"  2. Get a key from https://console.anthropic.com ($5 free)")
    else:  # gemini
        print(f"  1. Did you set $env:GEMINI_API_KEY in this PowerShell window?")
        print(f"  2. Is the key newly created? (fresh quota)")
        print(f"  3. Try: $env:LLM_MODEL=\"gemini-1.5-flash\"")
