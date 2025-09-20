from flask import Flask, render_template_string, request, jsonify
import os
import re
import time
import random
from datetime import datetime
import threading
import shutil
import json
import google.generativeai as genai

# --- Configuration ---
# Load the API key from an environment variable for security
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("No GOOGLE_API_KEY set for Flask application")
genai.configure(api_key=API_KEY)


# --- Flask App Initialization ---
app = Flask(__name__)

# --- Frontend HTML, CSS, and JavaScript ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TerminusAI</title>
<style>
/* --- Calm & Smooth Design --- */
:root {
    --bg-dark: #1a202c;
    --bg-light: #2d3748;
    --text-primary: #d1d5db;
    --text-secondary: #a0aec0;
    --accent: #4fd1c5;
    --border-color: #4a5568;
}
body { margin: 0; font-family: 'Fira Code', 'Consolas', monospace; background: var(--bg-dark); color: var(--text-primary); transition: background 0.3s ease; }
header { background: var(--bg-light); color: var(--accent); padding: 12px 20px; font-weight: bold; border-bottom: 1px solid var(--border-color); letter-spacing: 1px; }
#status { background: var(--bg-light); padding: 15px; margin: 10px; border-radius: 8px; border: 1px solid var(--border-color); }
#status p { margin: 5px 0; color: var(--text-secondary); }
#status p span { color: var(--text-primary); }
#ai-button { background: var(--accent); border: none; color: var(--bg-dark); padding: 5px 15px; border-radius: 20px; cursor: pointer; float: right; font-weight: bold; transition: all 0.3s ease; }
#ai-button:hover { transform: scale(1.05); box-shadow: 0 0 15px #4fd1c544; }
#terminal { background: var(--bg-light); padding: 15px; margin: 10px; height: 60vh; overflow-y: auto; border-radius: 8px; border: 1px solid var(--border-color); }
.prompt, .output { animation: fadeIn 0.5s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
.prompt { color: var(--accent); font-weight: bold; }
.output { color: var(--text-primary); margin: 2px 0; white-space: pre-wrap; }
#input { width: calc(100% - 42px); padding: 12px; margin: 10px; background: var(--bg-light); border: 1px solid var(--border-color); color: var(--accent); border-radius: 8px; font-family: inherit; font-size: 1em; transition: all 0.3s ease; }
#input::placeholder { color: var(--text-secondary); }
#input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 15px #4fd1c555; }
#ai-status.on { color: var(--accent); font-weight: bold; animation: glow 1.5s infinite alternate; }
@keyframes glow { from { text-shadow: 0 0 5px var(--accent); } to { text-shadow: 0 0 20px var(--accent), 0 0 30px var(--accent); } }
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg-light); }
::-webkit-scrollbar-thumb { background-color: var(--border-color); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background-color: var(--accent); }
</style>
</head>
<body>
<header>🚀 TerminusAI</header>
<div id="status">
    <p>🌟 Terminal Initialized</p>
    <p>📁 Working Directory: <span id="cwd"></span></p>
    <p>🤖 AI Mode: <span id="ai-status">OFF</span> <button id="ai-button">Toggle AI</button></p>
    <p>💡 Type 'help' for commands</p>
</div>
<div id="terminal"></div>
<input id="input" placeholder="Type a command..." autofocus />
<script>
let ai_mode = false;
const terminal = document.getElementById('terminal');
const input = document.getElementById('input');
const aiBtn = document.getElementById('ai-button');
const aiStatus = document.getElementById('ai-status');
const cwd = document.getElementById('cwd');
function appendLine(text, cls="output"){ const div = document.createElement('div'); div.className = cls; div.textContent = text; terminal.appendChild(div); terminal.scrollTop = terminal.scrollHeight; }
aiBtn.addEventListener('click', ()=>{ ai_mode = !ai_mode; aiStatus.textContent = ai_mode ? "ON" : "OFF"; if(ai_mode){ aiStatus.classList.add('on'); } else { aiStatus.classList.remove('on'); } });
async function updateCwd() { const res = await fetch('/get_cwd'); const data = await res.json(); cwd.textContent = data.cwd; }
input.addEventListener('keydown', async (e)=>{ if(e.key === 'Enter' && input.value.trim() !== ''){ const cmd = input.value; appendLine(`user@terminal:~$ ${cmd}`, "prompt"); input.value = ''; const res = await fetch('/execute', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:cmd, ai: ai_mode}) }); const data = await res.json(); appendLine(data.output); cwd.textContent = data.cwd; } });
updateCwd();
</script>
</body>
</html>
"""

# --- Backend Terminal Class ---
class WebTerminal:
    def __init__(self):
        self.current_dir = os.getcwd()
        self.processes = [{'pid':1,'name':'init','cpu':0.1,'memory':2.1},
                          {'pid':42,'name':'python-terminal','cpu':1.2,'memory':15.3}]
        threading.Thread(target=self._simulate_processes, daemon=True).start()
        try:
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            print(f"Failed to initialize Gemini model: {e}")
            self.model = None
    def _simulate_processes(self):
        while True:
            for p in self.processes:
                p['cpu'] = max(0.1, p['cpu'] + (random.random()-0.5)*2)
                p['memory'] = max(1, p['memory'] + (random.random()-0.5)*5)
            time.sleep(5)
    def _interpret_with_ai(self, text):
        if not self.model: return [], "AI model not initialized"
        prompt = f"""
        You are an expert command-line interpreter. Your task is to convert a user's natural language request into a sequence of shell commands.
        Rules:
        - The only available commands are: ls, ls -d */, cd, pwd, mkdir, touch, rm, mv, date, echo, ps.
        - You must respond ONLY with a valid JSON array of strings. Each string is a command to be executed.
        - You MUST invent a suitable filename if one is not provided (e.g., 'an html file' becomes 'index.html').
        - For chained commands (e.g., "create a folder and then put a file in it"), generate the commands in the correct sequence.
        - If the request is truly ambiguous, return an empty JSON array: [].
        Examples:
        "create mg folder and add one html file" -> ["mkdir mg", "touch mg/index.html"]
        "create test folder" -> ["mkdir test"]
        "show me the files" -> ["ls"]
        User Request: "{text}"
        JSON Array of Commands:
        """
        try:
            response = self.model.generate_content(prompt)
            json_text = response.text.strip()
            if json_text.startswith("```json"): json_text = json_text.replace("```json", "").replace("```", "").strip()
            elif json_text.startswith("```"): json_text = json_text.replace("```", "").strip()
            json_match = re.search(r'\[.*\]', json_text, re.DOTALL)
            if json_match: json_text = json_match.group()
            commands = json.loads(json_text)
            if isinstance(commands, list) and all(isinstance(c, str) for c in commands): return commands, None
            else: return [], "Invalid format returned by AI"
        except json.JSONDecodeError as e: return [], f"Failed to parse AI response: {str(e)}"
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower(): return [], "AI model not available. Check API key/model name."
            return [], f"AI service error: {str(e)}"
    def execute(self, cmd, ai=False):
        ai_message, commands_to_run = "", [cmd]
        if ai:
            interpreted_commands, error = self._interpret_with_ai(cmd)
            if error: ai_message = f"🤖 {error}. Trying as regular command."
            elif interpreted_commands:
                commands_to_run = interpreted_commands
                ai_message = f"🤖 AI interpreted '{cmd}' as: " + " && ".join(commands_to_run)
            else: ai_message = f"🤖 AI could not understand: '{cmd}'. Trying as regular command."
        final_output = ai_message + "\n\n" if ai_message else ""
        for single_cmd in commands_to_run:
            parts = single_cmd.strip().split()
            if not parts: continue
            base, args = parts[0], parts[1:]
            try:
                output = ""
                if base in ['ls','dir']: output = self._ls(args)
                elif base=='pwd': output = self.current_dir
                elif base=='cd': output = self._cd(args)
                elif base=='mkdir': output = self._mkdir(args)
                elif base=='touch': output = self._touch(args)
                elif base=='rm': output = self._rm(args)
                elif base=='mv': output = self._mv(args)
                elif base=='date': output = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                elif base=='echo': output = ' '.join(args)
                elif base=='ps': output = '\n'.join([f"{p['pid']} {p['name']} CPU:{p['cpu']:.1f}% MEM:{p['memory']:.1f}MB" for p in self.processes])
                elif base=='help': output = "Supported: ls, cd, pwd, mkdir, touch, rm, mv, date, echo, ps, help.\nAI mode understands natural language."
                else: output = f"Command not found: {base}"
                final_output += output + "\n"
            except Exception as e: final_output += f"Error executing '{single_cmd}': {str(e)}\n"
        if ai and len(commands_to_run) > 1: final_output += f"\n🤖 AI Summary: All operations completed!"
        return final_output.strip(), self.current_dir
    def _resolve_path(self, path): return os.path.abspath(os.path.join(self.current_dir, path.rstrip('/')))
    def _ls(self, args):
        if len(args) > 1 and args[0] == "-d" and args[1] == "*/":
            path = self.current_dir; dirs = [d + '/' for d in os.listdir(path) if os.path.isdir(os.path.join(path, d))]; return '  '.join(dirs) if dirs else "No directories found"
        path = self._resolve_path(args[0]) if args else self.current_dir
        if not os.path.exists(path): return f"No such directory: {path}"
        try: items = os.listdir(path); return '  '.join(items) if items else "Directory is empty"
        except Exception as e: return str(e)
    def _cd(self, args):
        if not args: return "cd: missing directory"
        new_path = self._resolve_path(args[0])
        if os.path.isdir(new_path): self.current_dir = new_path; return f"Changed directory to {self.current_dir}"
        return f"No such directory: {args[0]}"
    def _mkdir(self, args):
        if not args: return "mkdir: missing folder name"
        path = self._resolve_path(args[0])
        if os.path.exists(path): return f"Directory already exists: {args[0]}"
        try: os.makedirs(path, exist_ok=True); return f"Created directory: {args[0]}"
        except Exception as e: return str(e)
    def _touch(self, args):
        if not args: return "touch: missing file name"
        path = self._resolve_path(args[0])
        try:
            parent_dir = os.path.dirname(path)
            if parent_dir and not os.path.exists(parent_dir): os.makedirs(parent_dir, exist_ok=True)
            with open(path, 'a'): os.utime(path, None)
            return f"Created file: {args[0]}"
        except Exception as e: return str(e)
    def _rm(self, args):
        if not args: return "rm: missing operand"
        path_arg = args[1] if args[0] == "-r" and len(args) > 1 else args[0]
        path = self._resolve_path(path_arg)
        if not os.path.exists(path): return f"No such file/folder: {path_arg}"
        try:
            if os.path.isdir(path): shutil.rmtree(path); return f"Removed directory: {path_arg}"
            else: os.remove(path); return f"Removed file: {path_arg}"
        except Exception as e: return str(e)
    def _mv(self, args):
        if len(args) < 2: return "mv: missing source or destination"
        src, dst = self._resolve_path(args[0]), self._resolve_path(args[1])
        if not os.path.exists(src): return f"No such file/folder: {args[0]}"
        try: shutil.move(src, dst); return f"Moved {args[0]} to {args[1]}"
        except Exception as e: return str(e)

# --- Flask Routes ---
terminal = WebTerminal()
@app.route('/')
def index(): return render_template_string(HTML_PAGE)
@app.route('/execute', methods=['POST'])
def execute(): data = request.json; out, cwd = terminal.execute(data.get('command',''), data.get('ai', False)); return jsonify({'output': out, 'cwd': cwd})
@app.route('/get_cwd')
def get_cwd(): return jsonify({'cwd': terminal.current_dir})

# --- Main Execution ---
if __name__ == '__main__':
    # Gunicorn or another WSGI server will run the app in production
    app.run()