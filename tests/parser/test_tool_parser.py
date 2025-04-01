import unittest
from app.parser.tool_parser import parse_assistant_message, parse_tool_calls, parse_partial_tool_call


class TestToolParser(unittest.TestCase):
    def test_basic_tool_call(self):
        content = """I'll help you with that.
        
        <browser_use>
        <action>go_to_url</action>
        <url>https://example.com</url>
        </browser_use>
        
        Let me know what you see."""
        
        text_content, tool_calls = parse_assistant_message(content)
        
        self.assertIn("I'll help you with that", text_content)
        self.assertIn("Let me know what you see", text_content)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].name, "browser_use")
        self.assertEqual(tool_calls[0].parameters["action"], "go_to_url")
        self.assertEqual(tool_calls[0].parameters["url"], "https://example.com")
        self.assertFalse(tool_calls[0].partial)
    
    def test_multiple_tool_calls(self):
        content = """<read_file>
        <path>file1.txt</path>
        </read_file>
        
        Now let's check another file:
        
        <read_file>
        <path>file2.txt</path>
        </read_file>"""
        
        text_content, tool_calls = parse_assistant_message(content)
        
        self.assertIn("Now let's check another file", text_content)
        self.assertEqual(len(tool_calls), 2)
        self.assertEqual(tool_calls[0].name, "read_file")
        self.assertEqual(tool_calls[0].parameters["path"], "file1.txt")
        self.assertEqual(tool_calls[1].name, "read_file")
        self.assertEqual(tool_calls[1].parameters["path"], "file2.txt")
    
    def test_partial_tool_call(self):
        content = """Let me execute this command:
        
        <execute_command>
        <command>ls -la"""
        
        text_content, tool_calls = parse_assistant_message(content)
        
        self.assertIn("Let me execute this command", text_content)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].name, "execute_command")
        self.assertEqual(tool_calls[0].parameters.get("command"), "ls -la")
        self.assertTrue(tool_calls[0].partial)
    
    def test_nested_tags(self):
        content = """<write_to_file>
        <path>test.html</path>
        <content>
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test</title>
        </head>
        <body>
            <h1>Hello World</h1>
        </body>
        </html>
        </content>
        </write_to_file>"""
        
        text_content, tool_calls = parse_assistant_message(content)
        
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].name, "write_to_file")
        self.assertIn("<html>", tool_calls[0].parameters["content"])
        self.assertIn("<head>", tool_calls[0].parameters["content"])
