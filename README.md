# Enterprise Automation Framework

A comprehensive, AI-powered automation framework for UI, Mobile, and API testing with advanced features including LLM integration, RAGAS-powered test generation, and real-time synchronization.

## 🚀 Features

### Core Capabilities
- **Multi-Platform Testing**: Web UI, Mobile (real & simulator), API, and Database testing
- **AI-Powered Automation**: Natural language test case execution with LLM integration
- **Advanced Test Generation**: RAGAS framework integration for BRD/Swagger to test case generation
- **Real-Time Sync**: Bidirectional Excel↔SQL synchronization
- **Self-Healing**: AI-powered recovery with vision-based fallback
- **Comprehensive Reporting**: Allure integration with advanced analytics

### LLM Integration
- **Multi-Provider Support**: OpenAI, Google Gemini, Local Ollama
- **LangChain/LangGraph**: Optional framework integration
- **Dynamic Provider Selection**: Automatic fallback and priority-based selection
- **Advanced NLP**: Context-aware step parsing and classification

### Test Case Management
- **BRD Processing**: Extract user stories and generate comprehensive test cases
- **Swagger Integration**: API test case generation from OpenAPI specifications
- **Excel Processing**: Enhanced Excel file processing with categorization
- **Version Control**: Complete versioning and conflict resolution
- **Real-Time Dashboard**: Modern web interface with live updates

## 📋 Requirements

### System Requirements
- Python 3.8+
- Windows 10/11, macOS 10.15+, or Linux
- 4GB RAM minimum (8GB recommended)
- 2GB free disk space

### Dependencies
```bash
# Core dependencies
pip install fastapi uvicorn pandas requests pytest allure-pytest jinja2

# LLM providers (optional)
pip install openai google-generativeai ollama

# LangChain/LangGraph (optional)
pip install langchain langgraph

# RAGAS framework (optional)
pip install ragas

# Web automation
pip install playwright

# Mobile automation
pip install appium-python-client

# Database
pip install sqlite3

# Additional utilities
pip install pyyaml python-multipart
```

## 🛠️ Installation

### Quick Start

1. **Clone the repository**
```bash
git clone <repository-url>
cd enterprise_automation_framework_final
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Install Playwright browsers**
```bash
playwright install
```

4. **Configure settings**
```bash
# Copy and edit settings.yaml
cp settings.yaml.example settings.yaml
# Edit settings.yaml with your configuration
```

5. **Start the dashboard**
```bash
python -m dashboard.app
```

6. **Access the dashboard**
Open http://localhost:8000 in your browser

### Detailed Installation

#### 1. Environment Setup

**Windows:**
```bash
# Install Python 3.8+ from python.org
# Install Git from git-scm.com
# Open PowerShell as Administrator
Set-ExecutionPolicy RemoteSigned
```

**macOS:**
```bash
# Install Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.9

# Install Git
brew install git
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install python3.9 python3-pip git
```

#### 2. Framework Installation

```bash
# Clone repository
git clone <repository-url>
cd enterprise_automation_framework_final

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install
```

#### 3. Configuration

Create and configure `settings.yaml`:

```yaml
# LLM Configuration
llm_mode: "local"  # local, cloud, auto
model: "gemini"     # gpt-3.5-turbo, gemini-pro, llama2

# LLM Providers
llm_providers:
  - name: "openai"
    type: "cloud"
    enabled: true
    priority: 1
    config:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-3.5-turbo"
  - name: "gemini"
    type: "cloud"
    enabled: true
    priority: 2
    config:
      api_key: "${GEMINI_API_KEY}"
      model: "gemini-pro"
  - name: "ollama"
    type: "local"
    enabled: true
    priority: 3
    config:
      host: "http://localhost:11434"
      model: "llama2"

# Database Configuration
database:
  url: "sqlite:///./test_sets.db"
  sync_enabled: true
  real_time_sync: true

# Dashboard Configuration
dashboard:
  host: "0.0.0.0"
  port: 8000
  debug: false
```

#### 4. LLM Setup

**OpenAI Setup:**
```bash
export OPENAI_API_KEY="your-openai-api-key"
```

**Google Gemini Setup:**
```bash
export GEMINI_API_KEY="your-gemini-api-key"
```

**Local Ollama Setup:**
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull llama2
ollama pull codellama
ollama pull mistral
```

#### 5. Mobile Testing Setup

**Android Setup:**
```bash
# Install Android Studio
# Install Android SDK
# Set ANDROID_HOME environment variable
export ANDROID_HOME="/path/to/android/sdk"

# Install Appium
npm install -g appium

# Start Appium server
appium
```

**iOS Setup (macOS only):**
```bash
# Install Xcode
# Install Appium
npm install -g appium

# Install WebDriverAgent
# Configure iOS simulator
```

## 🎯 Usage Examples

### 1. BRD to Test Case Generation

```python
from utils.ragas_utils import generate_test_cases_with_ragas

# Generate test cases from BRD
test_cases = generate_test_cases_with_ragas(
    brd_path="docs/sample_brd.xlsx",
    created_by="system",
    max_cases=20
)

print(f"Generated {len(test_cases)} test cases")
```

### 2. Swagger to API Test Cases

```python
from utils.ragas_utils import generate_test_cases_from_swagger

# Generate API test cases from Swagger
api_cases = generate_test_cases_from_swagger(
    swagger_path="api/swagger.json",
    created_by="system",
    max_cases=30
)

print(f"Generated {len(api_cases)} API test cases")
```

### 3. Natural Language Test Execution

```python
from llm_integration.llm_agent import LLMAgent
from src.automation_framework.mcp_router import MCPRouter

# Initialize LLM agent
llm_agent = LLMAgent(config)

# Parse natural language step
step = llm_agent.parse_natural_language_step("Click the login button")
print(f"Parsed step: {step}")

# Execute test case
router = MCPRouter(config, reporter)
router.run_test_case(test_case)
```

### 4. Dashboard Usage

1. **Upload BRD/Swagger**: Use the dashboard to upload Business Requirements Documents or Swagger specifications
2. **Generate Test Cases**: Automatically generate positive, negative, and boundary test cases
3. **Edit Test Cases**: Modify test cases in the web interface
4. **Execute Tests**: Run tests with real-time status monitoring
5. **View Reports**: Access Allure reports and analytics

## 🔧 Configuration

### LLM Configuration

The framework supports multiple LLM providers with automatic fallback:

```yaml
llm_mode: "auto"  # Automatically select best available provider

llm_providers:
  - name: "openai"
    type: "cloud"
    enabled: true
    priority: 1
    config:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-3.5-turbo"
      timeout: 30
      max_tokens: 2048
```

### Self-Healing Configuration

```yaml
mcp:
  max_retries: 3
  retry_interval_seconds: 2
  self_healing_enabled: true
  vision_fallback_enabled: true
  ai_powered_recovery: true
```

### Database Configuration

```yaml
database:
  url: "sqlite:///./test_sets.db"
  sync_enabled: true
  auto_backup: true
  backup_interval_hours: 24
  real_time_sync: true
```

## 📊 Architecture

### High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Dashboard     │    │   LLM Agent     │    │   MCP Router    │
│   (FastAPI)     │◄──►│   (Multi-       │◄──►│   (Test         │
│                 │    │   Provider)     │    │   Execution)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Database      │    │   RAGAS Utils   │    │   MCPs          │
│   (SQLite)      │    │   (Test Gen)    │    │   (UI/Mobile/   │
│                 │    │                 │    │    API/SQL)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Data Flow

```
1. User uploads BRD/Swagger → RAGAS Utils
2. RAGAS generates test cases → Database
3. User edits test cases → Dashboard ↔ Database
4. User executes tests → MCP Router
5. MCP Router → LLM Agent (classification)
6. LLM Agent → Appropriate MCP (UI/Mobile/API/SQL)
7. MCP executes test → Reporter
8. Reporter → Allure Reports
```

### Test Execution Flow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Natural     │───►│ LLM Agent   │───►│ MCP Router  │───►│ UI MCP      │
│ Language    │    │ (Parse &    │    │ (Route to   │    │ (Playwright)│
│ Step        │    │ Classify)   │    │ Correct MCP)│    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                              │
                                                              ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Allure      │◄───│ Reporter    │◄───│ Self-       │◄───│ Test        │
│ Reports     │    │ (Log        │    │ Healing     │    │ Execution   │
│             │    │ Results)    │    │ (AI/        │    │             │
│             │    │             │    │ Vision)     │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

## 🔍 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with Allure reporting
pytest --alluredir=reports/allure

# Run specific test categories
pytest tests/test_ui.py
pytest tests/test_api.py
pytest tests/test_mobile.py

# Run integration tests
python integration_test.py
```

### Test Categories

- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end workflow testing
- **UI Tests**: Web automation testing
- **API Tests**: REST API testing
- **Mobile Tests**: Mobile app testing
- **Database Tests**: SQL query testing

## 📈 Monitoring and Reporting

### Dashboard Features

- **Real-time Statistics**: Test case counts, execution status
- **Live Execution Monitoring**: Real-time test execution status
- **Advanced Filtering**: Filter by category, priority, tags
- **Excel Export/Import**: Bidirectional Excel synchronization
- **Version Control**: Test case versioning and comparison

### Allure Reports

- **Comprehensive Reports**: Detailed test execution reports
- **Screenshot Capture**: Automatic screenshot on failure
- **Performance Metrics**: Execution time and resource usage
- **Trend Analysis**: Historical execution trends
- **Export Options**: HTML, PDF, Excel export

## 🚨 Troubleshooting

### Common Issues

**1. LLM Provider Not Available**
```bash
# Check API keys
echo $OPENAI_API_KEY
echo $GEMINI_API_KEY

# Test Ollama
curl http://localhost:11434/api/tags
```

**2. Playwright Installation Issues**
```bash
# Reinstall Playwright
pip uninstall playwright
pip install playwright
playwright install
```

**3. Database Connection Issues**
```bash
# Check database file
ls -la test_sets.db

# Reset database
rm test_sets.db
python -c "from utils.db_utils import Database; db = Database('test_sets.db')"
```

**4. Dashboard Not Starting**
```bash
# Check port availability
netstat -an | grep 8000

# Use different port
python -m dashboard.app --port 8001
```

### Logging

Enable detailed logging:

```yaml
logging:
  level: "DEBUG"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/automation.log"
```

### Performance Optimization

```yaml
# Concurrency settings
concurrency:
  enabled: true
  workers: 4
  max_workers: 8

# LLM optimization
llm_framework:
  temperature: 0.1
  max_tokens: 2048
  timeout: 30
```

## 🔧 Development

### Project Structure

```
enterprise_automation_framework_final/
├── api/                    # API testing components
├── dashboard/              # Web dashboard
├── llm_integration/        # LLM agent and providers
├── mobile/                 # Mobile testing components
├── src/automation_framework/
│   ├── mcp/               # Model Context Protocols
│   ├── utils/             # Utility functions
│   ├── security/          # Authentication
│   └── versioning/        # Version control
├── tests/                 # Test files
├── utils/                 # Legacy utilities
├── web/                   # Web testing components
├── config/                # Configuration files
├── data/                  # Test data
├── reports/               # Allure reports
├── screenshots/           # Screenshots
├── settings.yaml          # Main configuration
├── requirements.txt       # Dependencies
└── README.md             # This file
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

### Code Quality

```bash
# Run linting
flake8 .
pylint src/
black --check .

# Run type checking
mypy src/

# Run security checks
bandit -r src/
```

## 📚 API Reference

### LLM Agent

```python
from llm_integration.llm_agent import LLMAgent

agent = LLMAgent(config)

# Parse natural language
step = agent.parse_natural_language_step("Click login button")

# Classify test type
test_type = agent.classify("Navigate to login page")

# Translate API command
api_request = agent.translate_api("GET /api/users")

# Generate test cases
test_cases = agent.generate_test_cases_from_brd(brd_content)
```

### MCP Router

```python
from src.automation_framework.mcp_router import MCPRouter

router = MCPRouter(config, reporter)

# Run single test case
router.run_test_case(test_case)

# Run multiple test cases
router.run_all(test_cases)
```

### Database Utils

```python
from utils.db_utils import Database

db = Database("test_sets.db")

# Add test case
case_id = db.add_test_case(test_case)

# Get test cases
test_cases = db.get_test_cases()

# Add test run
run_id = db.add_test_run(case_id, "running")
```

## 🎯 Best Practices

### Test Case Design

1. **Use Natural Language**: Write test steps in plain English
2. **Include Context**: Provide sufficient context for LLM understanding
3. **Categorize Properly**: Use appropriate categories (positive, negative, boundary)
4. **Set Priorities**: Assign realistic priorities based on business impact
5. **Add Tags**: Use descriptive tags for better organization

### Configuration Management

1. **Environment Variables**: Use environment variables for sensitive data
2. **Configuration Files**: Keep configuration in YAML files
3. **Version Control**: Track configuration changes
4. **Backup**: Regular database and configuration backups

### Performance Optimization

1. **Concurrent Execution**: Enable parallel test execution
2. **LLM Caching**: Use LLM response caching
3. **Resource Management**: Monitor memory and CPU usage
4. **Database Optimization**: Regular database maintenance

## 📞 Support

### Getting Help

1. **Documentation**: Check this README and inline documentation
2. **Issues**: Report issues on GitHub
3. **Discussions**: Use GitHub Discussions for questions
4. **Examples**: Check the `tests/` directory for examples

### Community

- **GitHub**: [Repository](https://github.com/your-repo)
- **Discussions**: [GitHub Discussions](https://github.com/your-repo/discussions)
- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Playwright**: For web automation capabilities
- **Appium**: For mobile automation
- **Allure**: For comprehensive reporting
- **RAGAS**: For test case generation
- **LangChain**: For LLM framework integration
- **FastAPI**: For modern web framework

---

**Enterprise Automation Framework** - Making AI-powered testing accessible to everyone.