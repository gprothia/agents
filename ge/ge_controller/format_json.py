import json
import os

f_path = '/Users/prothiag/code/agents/ge/ge_controller/1.json'
if not os.path.exists(f_path):
    print(f"Error: {f_path} does not exist")
    exit(1)

content = open(f_path, 'r').read().strip()
if not content:
    print("Error: File is empty")
    exit(1)

if content.startswith("Agent found:"):
    dict_str = content[len("Agent found:"):].strip()
else:
    dict_str = content

try:
    # Define JSON/Python keywords in local scope for safe evaluation
    local_scope = {
        "true": True,
        "false": False,
        "null": None,
        "True": True,
        "False": False,
        "None": None
    }
    
    # Evaluate safely without exposing builtins
    data = eval(dict_str, {"__builtins__": {}}, local_scope)
    formatted_json = json.dumps(data, indent=2)
    
    # Only write to the file if parsing succeeded
    with open(f_path, 'w') as f:
        f.write(formatted_json)
    print("Success: 1.json has been beautifully formatted into a multi-line JSON!")
except Exception as e:
    print(f"Error parsing content: {e}")
