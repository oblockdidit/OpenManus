# Pre-Call Research Agent

A specialized AI agent that automates the research process before sales calls for your web development business. This tool analyzes existing websites, prepares tailored talking points, and generates insightful questions for your sales team to use during calls.

## Purpose

The Pre-Call Research Agent helps web development sales representatives prepare thoroughly before contacting leads by:

1. **Website Analysis**: Evaluating existing websites for quality, performance, and technology
2. **Industry-Specific Insights**: Providing relevant insights based on the business's industry
3. **Sales Preparation**: Suggesting questions, talking points, and objection handling strategies
4. **Technical Expertise**: Identifying technical issues that can be addressed during the call

## Key Features

- 🔍 **Website Evaluation**: Scores websites on design, performance, mobile compatibility, and SEO
- 🔧 **Technology Detection**: Identifies the tech stack and platforms used by prospects
- 💡 **Question Generation**: Creates focused, open-ended questions for sales conversations
- 🚧 **Pain Point Identification**: Highlights likely issues prospects are experiencing
- 🗣️ **Objection Handling**: Anticipates common objections with prepared responses

## Setup

### 1. Environment Setup

Create a Python virtual environment and install dependencies:

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install additional required packages
pip install httpx aiohttp

# Install browser automation dependencies
playwright install
```

### 2. Configuration

Create a `.env` file with the following environment variables:

```
TWENTY_API_URL=https://api.twenty.com
TWENTY_API_KEY=your_api_key
OPENAI_API_KEY=your_openai_key
```

## Usage

This tool is designed to be run when a lead is ready for a sales call. It can work in two modes:

### 1. CRM Mode

Get lead data from Twenty CRM and analyze it:

```bash
python lead_prospector.py --mode crm --company-id "company-id-here"
```

### 2. DB Record Mode

Analyze a lead directly from your database record:

```bash
# Create a JSON file with the lead data
python lead_prospector.py --mode db-record --db-record "path/to/lead_record.json"
```

Example JSON format:

```json
{
  "_id": "678760b504fabf0a7a81a51b",
  "name": "Loaf Mcr",
  "website": "loafmcr.com",
  "industry": "Bakeries",
  "address": "Affinity Riverview, 29 New Bailey St, Manchester, Salford M3 5GN",
  "phoneNumber": "07961 156011"
}
```

## Research Output

The agent produces comprehensive pre-call research including:

1. **Website Analysis**:
   - Design, performance, mobile, and SEO scores
   - Identified technologies
   - Key technical issues

2. **Sales Call Preparation**:
   - 3-5 tailored questions to ask
   - Industry-specific talking points
   - Common objection handling strategies
   - Proposed solution outline

3. **Pain Points**:
   - Likely issues the prospect is experiencing
   - Areas where your services can provide value

## Integration with Your Workflow

The Pre-Call Research Agent is designed to fit into your existing sales workflow:

1. **Lead Ready for Call**: When a lead is ready to be contacted
2. **Run Research**: Execute the agent with the lead's information
3. **Review Research**: Sales rep reviews the generated materials
4. **Make Call**: Use the insights and questions during the sales call
5. **Update CRM**: Record call outcomes in your CRM system