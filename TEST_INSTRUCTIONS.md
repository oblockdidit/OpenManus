# Testing the OpenManus + Twenty CRM Integration

This guide provides step-by-step instructions for testing the OpenManus + Twenty CRM integration for pre-call research.

## Prerequisites

Before starting, ensure you have:

1. API keys for Twenty CRM and OpenAI
2. Python environment set up (Python 3.10+ recommended)
3. All dependencies installed

## Setup Steps

1. **Configure Environment Variables**

   Set the necessary API keys:

   ```bash
   # For Bash/Zsh
   export TWENTY_API_URL="https://api.twenty.com"
   export TWENTY_API_KEY="your_twenty_api_key"
   export OPENAI_API_KEY="your_openai_api_key"
   
   # For Windows CMD
   set TWENTY_API_URL=https://api.twenty.com
   set TWENTY_API_KEY=your_twenty_api_key
   set OPENAI_API_KEY=your_openai_api_key
   
   # For Windows PowerShell
   $env:TWENTY_API_URL = "https://api.twenty.com"
   $env:TWENTY_API_KEY = "your_twenty_api_key"
   $env:OPENAI_API_KEY = "your_openai_api_key"
   ```

## Test Connectivity

First, let's test basic connectivity to ensure all APIs are accessible:

```bash
# Make it executable if needed
chmod +x /Users/teez/Development/Claude/OpenManus/test_connectivity.py

# Run the test
cd /Users/teez/Development/Claude/OpenManus
python test_connectivity.py
```

This will verify:
- Connection to Twenty CRM API
- Connection to OpenAI/Claude API
- Ability to load the test database record

## Testing Pre-Call Research Agent

If the connectivity test passes, you can test the full pre-call research agent:

### Using Database Record

```bash
cd /Users/teez/Development/Claude/OpenManus
python lead_prospector.py --mode db-record --db-record test_db_record.json
```

### Using Twenty CRM Record

If you have a record already in Twenty CRM:

```bash
cd /Users/teez/Development/Claude/OpenManus
python lead_prospector.py --mode crm --company-id "your-company-id"
```

## Troubleshooting

If you encounter issues:

1. **API Connection Errors**:
   - Verify API keys are correct
   - Check network connectivity
   - Ensure API endpoints are accessible

2. **Module Import Errors**:
   - Verify all dependencies are installed
   - Check if you're in the correct directory

3. **Configuration Issues**:
   - Ensure config.toml is properly formatted
   - Verify environment variables are set correctly

4. **Browser Automation Issues**:
   - Install browser dependencies: `playwright install`
   - Try with headless mode: Edit config.toml to set `headless = true`

## Expected Output

A successful test should output a detailed pre-call research report including:

- Website analysis (if a website exists)
- Questions to ask during the call
- Industry-specific talking points
- Potential objections and handling strategies
- Proposed solutions tailored to the prospect's needs

The output will be displayed in the terminal and can be redirected to a file if needed.