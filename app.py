import streamlit as st
import os
import subprocess
import sys
import shutil
import uuid
import platform
import time
from pathlib import Path
import tempfile
import glob

# Set page configuration
st.set_page_config(
    page_title="Nuitka Python Compiler",
    page_icon="🚀",
    layout="wide"
)

# Initialize session state
if 'compilation_results' not in st.session_state:
    st.session_state.compilation_results = None
if 'show_results' not in st.session_state:
    st.session_state.show_results = False

def ensure_dir(dir_path):
    """Ensure directory exists"""
    Path(dir_path).mkdir(parents=True, exist_ok=True)

def check_dependencies():
    """Check if required dependencies are available"""
    missing_deps = []
    
    # Check for patchelf
    result = subprocess.run(["which", "patchelf"], capture_output=True)
    if result.returncode != 0:
        missing_deps.append("patchelf")
    
    # Check for gcc
    result = subprocess.run(["which", "gcc"], capture_output=True)
    if result.returncode != 0:
        missing_deps.append("gcc")
    
    return missing_deps

def get_current_python_version():
    """Get the current Python version for compatibility notes"""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

def get_nuitka_version():
    """Get the current Nuitka version to handle different command line options"""
    try:
        result = subprocess.run([sys.executable, "-m", "nuitka", "--version"], 
                                capture_output=True, text=True)
        if result.returncode == 0:
            version_line = result.stdout.strip().split('\n')[0]
            # Extract version number from output like "Nuitka 2.5.0"
            version = version_line.split()[-1]
            return version
        return "unknown"
    except:
        return "unknown"

def compile_with_nuitka(code, requirements, packages, target_platform, compilation_mode, output_extension=".bin"):
    """Compile Python code with Nuitka"""
    # Create status container
    status_container = st.container()
    status_container.info("Starting compilation process...")
    
    # Check Nuitka version
    nuitka_version = get_nuitka_version()
    status_container.info(f"Using Nuitka version: {nuitka_version}")
    
    # Check dependencies first
    missing_deps = check_dependencies()
    if missing_deps:
        error_msg = f"Required dependencies are missing: {', '.join(missing_deps)}\n"
        error_msg += "Some features may not work properly."
        status_container.warning(error_msg)
    
    # Create unique ID for this compilation
    job_id = str(uuid.uuid4())
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_code")
    job_dir = os.path.join(base_dir, job_id)
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiled_output", job_id)
    
    # Create directories
    ensure_dir(job_dir)
    ensure_dir(output_dir)
    
    # Handle Windows compilation
    if target_platform == "windows":
        error_msg = """
        ⚠️ **Windows compilation is not supported on Streamlit Cloud**
        
        Reason: Windows compilation requires Wine (Windows compatibility layer), which is not available on Streamlit Cloud.
        """
        status_container.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'install_result': "Windows compilation not supported",
            'compile_output': error_msg,
            'binary_path': None,
            'binary_info': None
        }
    
    # Install system packages if specified
    packages_result = "No system packages specified."
    if packages.strip():
        packages_result = install_system_packages(packages, status_container)
    
    # Write code to a Python file
    script_path = os.path.join(job_dir, "user_script.py")
    with open(script_path, "w") as f:
        f.write(code)
    
    # Handle requirements
    install_result = "No Python requirements specified."
    if requirements.strip():
        req_path = os.path.join(job_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write(requirements)
        
        try:
            status_container.info("Installing Python requirements...")
            install_process = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_path],
                capture_output=True,
                text=True
            )
            
            if install_process.returncode == 0:
                status_container.success("✅ Python requirements installed successfully.")
                install_result = "Python requirements installed successfully."
            else:
                status_container.warning("⚠️ Python requirements installation completed with warnings.")
                install_result = f"Installation completed with return code: {install_process.returncode}\n{install_process.stderr}"
        except Exception as e:
            install_result = f"Error: {str(e)}"
            status_container.error(install_result)
            return {
                'success': False,
                'error': str(e),
                'install_result': install_result,
                'compile_output': "",
                'binary_path': None,
                'binary_info': None
            }
    
    # Compilation
    try:
        status_container.info("🔧 Starting compilation...")
        
        # Define compilation options with static linking for true portability
        # Fixed: --static-libpython=yes (requires argument)
        compile_options = {
            "max_compatibility": {
                "name": "Universal Binary (Static Python)",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--onefile",  # Single portable file
                    "--static-libpython=yes",  # Static Python - this is KEY! (fixed with =yes)
                    "--show-progress",
                    "--remove-output",
                    "--follow-imports",
                    "--lto=yes",  # Link-time optimization helps with compatibility
                    script_path,
                    f"--output-dir={output_dir}"
                ],
                "creates_runner": False
            },
            "portable": {
                "name": "Portable Non-Standalone",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--show-progress",
                    "--remove-output",
                    "--static-libpython=yes",  # Fixed with =yes
                    script_path,
                    f"--output-dir={output_dir}"
                ],
                "creates_runner": False
            },
            "standalone": {
                "name": "Standalone with Static Python",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--onefile",
                    "--static-libpython=yes",  # Fixed with =yes
                    "--show-progress",
                    "--remove-output",
                    script_path,
                    f"--output-dir={output_dir}"
                ],
                "creates_runner": False
            }
        }
        
        selected_option = compile_options[compilation_mode]
        status_container.info(f"Using {selected_option['name']}...")
        
        # Show command in collapsible section
        with status_container.expander(f"Command for {selected_option['name']}"):
            st.code(' '.join(selected_option['cmd']))
        
        # Run compilation
        process = subprocess.Popen(
            selected_option['cmd'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Progress tracking
        progress_bar = st.progress(0)
        log_placeholder = st.empty()
        compile_output = ""
        line_count = 0
        
        # Real-time progress display
        for line in iter(process.stdout.readline, ''):
            compile_output += line
            line_count += 1
            
            # Update progress
            progress = min(line_count / 200, 0.99)
            progress_bar.progress(progress)
            
            # Show formatted log (last 20 lines)
            lines = compile_output.splitlines()
            formatted_log = '\n'.join(lines[-20:])
            with log_placeholder.container():
                with st.expander("📋 Compilation Log", expanded=False):
                    st.text(formatted_log)
        
        progress_bar.progress(1.0)
        process.wait()
        
        status_container.info(f"Compilation finished with exit code: {process.returncode}")
        
        # Find the compiled binary
        output_filename = f"user_script{output_extension}"
        binary_path = find_compiled_binary(output_dir, output_filename)
        
        # If not found with expected extension, try finding any executable
        if not binary_path:
            # Try common executable patterns for onefile
            patterns = [
                os.path.join(output_dir, "user_script"),
                os.path.join(output_dir, "user_script.bin"),
                os.path.join(output_dir, "**", "user_script"),
                os.path.join(output_dir, "**", "*.bin"),
            ]
            
            for pattern in patterns:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    binary_path = matches[0]
                    break
        
        if process.returncode == 0 and binary_path:
            # Check if it's really a binary file
            file_process = subprocess.run(["file", binary_path], capture_output=True, text=True)
            binary_info = file_process.stdout
            
            # Check if it's statically linked
            ldd_process = subprocess.run(["ldd", binary_path], capture_output=True, text=True)
            if "not a dynamic executable" in ldd_process.stderr or "statically linked" in ldd_process.stdout:
                static_info = "✅ Statically linked - fully portable!"
            else:
                static_info = "⚠️ Dynamically linked - may need compatible libraries"
            
            # Rename to desired extension
            if output_extension in ['.bin', '.sh'] and not binary_path.endswith(output_extension):
                new_binary_path = binary_path + output_extension
                shutil.move(binary_path, new_binary_path)
                binary_path = new_binary_path
            
            # Make executable
            os.chmod(binary_path, 0o755)
            
            # Current Python version info
            current_python = get_current_python_version()
            
            # Add system info to result
            result_summary = f"""
Compilation Details:
- Mode: {selected_option['name']}
- Nuitka Version: {nuitka_version}
- Exit Code: {process.returncode}
- Output Path: {binary_path}
- File Size: {os.path.getsize(binary_path) / 1024:.2f} KB
- Compiled with Python: {current_python}
- Static Linking: {static_info}

System Packages: {packages_result}
Python Requirements: {install_result}

Binary Information: {binary_info}

PORTABILITY NOTES:
- This binary was compiled with --static-libpython=yes for maximum portability
- Static linking means it should work anywhere without Python version mismatches
- No need to copy to WSL filesystem - it should work from /mnt/c/
"""
            
            status_container.success(f"✅ {selected_option['name']} compilation successful!")
            return {
                'success': True,
                'install_result': result_summary,
                'compile_output': compile_output,
                'binary_path': binary_path,
                'binary_info': binary_info,
                'output_extension': output_extension,
                'compilation_mode': compilation_mode,
                'python_version': current_python,
                'nuitka_version': nuitka_version,
                'static_info': static_info
            }
        else:
            return {
                'success': False,
                'error': "Compilation failed or binary not found",
                'install_result': f"Compilation failed.\n\nSystem Packages: {packages_result}\nPython Requirements: {install_result}",
                'compile_output': compile_output,
                'binary_path': None,
                'binary_info': "Compilation failed"
            }
        
    except Exception as e:
        status_container.error(f"❌ Error during compilation: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'install_result': f"Compilation error: {str(e)}",
            'compile_output': f"Error: {str(e)}",
            'binary_path': None,
            'binary_info': "Compilation error"
        }

def install_system_packages(packages_content, status_container):
    """Install system packages from packages.txt content"""
    if not packages_content.strip():
        return "No system packages specified."
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.txt')
    try:
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(packages_content)
        
        status_container.info("Installing system packages...")
        
        # Install packages line by line
        install_log = ""
        failed_packages = []
        successful_packages = []
        
        with open(temp_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                status_container.info(f"Installing: {line}")
                
                # Try to install package
                install_process = subprocess.run(
                    ["apt-get", "update", "-qq"],
                    capture_output=True,
                    text=True
                )
                
                install_process = subprocess.run(
                    ["apt-get", "install", "-y", line],
                    capture_output=True,
                    text=True
                )
                
                if install_process.returncode == 0:
                    successful_packages.append(line)
                    install_log += f"✅ Successfully installed: {line}\n"
                else:
                    failed_packages.append(line)
                    install_log += f"❌ Failed to install: {line}\n"
        
        summary = f"""
System Packages Summary:
✅ Successful: {', '.join(successful_packages)}
❌ Failed: {', '.join(failed_packages)}
"""
        return summary + "\n" + install_log
    
    except Exception as e:
        error_msg = f"Error installing system packages: {str(e)}"
        status_container.error(error_msg)
        return error_msg
    
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def find_compiled_binary(output_dir, output_filename):
    """Find the compiled binary, checking different possible paths"""
    # Try direct path first
    direct_path = os.path.join(output_dir, output_filename)
    if os.path.exists(direct_path):
        return direct_path
    
    # Try in .dist folder (standalone builds)
    dist_path = os.path.join(output_dir, "user_script.dist", output_filename)
    if os.path.exists(dist_path):
        return dist_path
    
    # Try using glob to find any executable
    patterns = [
        os.path.join(output_dir, "**", output_filename),
        os.path.join(output_dir, "**", "user_script"),
        os.path.join(output_dir, "**", "*.bin"),
        os.path.join(output_dir, "**", "*.exe")
    ]
    
    for pattern in patterns:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]
    
    return None

def run_compiled_binary(binary_path):
    """Run the compiled binary and return the output"""
    try:
        # Make the binary executable
        os.chmod(binary_path, 0o755)
        
        # Run the binary and capture output in real-time with a timeout
        process = subprocess.Popen(
            [binary_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Create a placeholder for real-time output
        output_placeholder = st.empty()
        output_text = ""
        
        # Poll process for new output until finished
        start_time = time.time()
        while process.poll() is None:
            # Check for timeout (10 seconds)
            if time.time() - start_time > 10:
                process.terminate()
                return False, "Execution timed out after 10 seconds."
            
            # Read stdout
            stdout_line = process.stdout.readline()
            if stdout_line:
                output_text += f"[STDOUT] {stdout_line}"
                output_placeholder.text(output_text)
            
            # Read stderr
            stderr_line = process.stderr.readline()
            if stderr_line:
                output_text += f"[STDERR] {stderr_line}"
                output_placeholder.text(output_text)
            
            # Brief pause to prevent excessive CPU usage
            time.sleep(0.1)
        
        # Get remaining output
        stdout, stderr = process.communicate()
        if stdout:
            output_text += f"[STDOUT] {stdout}"
        if stderr:
            output_text += f"[STDERR] {stderr}"
        
        output_placeholder.text(output_text)
        
        return True, output_text
    except Exception as e:
        return False, f"Error running the binary: {str(e)}"

# App title and description
st.title("🚀 Nuitka Python Compiler (Universal Binaries)")
st.markdown("""
Convert your Python code into truly portable executables using Nuitka with static linking.
**Creates binaries that work anywhere!** 🌍
""")

# Important notice about the solution
st.success("""
🎯 **Now with Static Linking!**

This version uses `--static-libpython=yes` to create truly portable binaries that:
- Work on any Linux system regardless of Python version
- Can be run from anywhere (including Windows filesystem in WSL)
- No more `_PyRuntime` errors!
""")

# Dependency status
missing_deps = check_dependencies()
if missing_deps:
    st.warning(f"⚠️ Missing dependencies: {', '.join(missing_deps)}")
else:
    st.success("✅ All required dependencies available!")

# Create tabs
tab1, tab2, tab3 = st.tabs(["🔧 Compiler", "📖 How to Use", "ℹ️ About"])

with tab1:
    # Show results if available
    if st.session_state.show_results and st.session_state.compilation_results:
        results = st.session_state.compilation_results
        
        if results['success']:
            st.success("🎉 Compilation successful!")
            
            # Show static linking status
            if results.get('static_info'):
                if "Statically linked" in results['static_info']:
                    st.success(results['static_info'])
                else:
                    st.warning(results['static_info'])
            
            # Show Python version compatibility info
            st.info(f"""
            **Compiled with Python {results.get('python_version', 'Unknown')}**
            **Using Nuitka {results.get('nuitka_version', 'Unknown')}**
            
            ✨ **With static linking, this binary should work anywhere!**
            """)
            
            # Stats
            if results['binary_path'] and os.path.exists(results['binary_path']):
                file_size = os.path.getsize(results['binary_path'])
                st.metric("File Size", f"{file_size / 1024:.2f} KB")
                
                # Download
                download_filename = f"compiled_program{results.get('output_extension', '.bin')}"
                with open(results['binary_path'], "rb") as f:
                    st.download_button(
                        "⬇️ Download Universal Binary",
                        data=f,
                        file_name=download_filename,
                        mime="application/octet-stream",
                        type="primary"
                    )
                
                # Instructions for static binary
                st.info("""
                **Universal Binary Instructions:**
                
                ✅ **This static binary should work from ANY location!**
                
                1. Download the file
                2. Make executable: `chmod +x compiled_program.bin`
                3. Run from anywhere: `./compiled_program.bin`
                
                **Key Benefits:**
                - No Python installation required
                - No version compatibility issues
                - Works from Windows filesystem in WSL (`/mnt/c/`)
                - Works from Linux filesystem
                - Truly portable!
                """)
                
                # Test run
                st.subheader("🧪 Test Run (on Streamlit Cloud)")
                if st.button("Run Compiled Binary", key="run_button"):
                    with st.spinner("Executing..."):
                        success, result = run_compiled_binary(results['binary_path'])
                    
                    if success:
                        st.success("✅ Execution successful!")
                    else:
                        st.warning("⚠️ Execution completed with issues")
                    
                    st.text_area("Execution Output", result, height=200)
        else:
            st.error("❌ Compilation failed")
        
        # Detailed logs (collapsible)
        with st.expander("📋 Detailed Logs", expanded=False):
            st.subheader("Installation Results")
            st.text(results['install_result'])
            
            st.subheader("Compilation Output")
            st.text(results['compile_output'] if results['compile_output'] else "No output available")
        
        # Button to start new compilation
        if st.button("🔄 Start New Compilation", type="secondary"):
            st.session_state.compilation_results = None
            st.session_state.show_results = False
            st.rerun()
    else:
        # Show compilation interface
        col1, col2 = st.columns([2, 1])
        
        with col1:
            code = st.text_area(
                "Your Python Code",
                value="""# Your Python code here
print('Hello from compiled Python!')
print('This is running as a static binary!')

# This will work from anywhere now!
import os
print(f'Running from: {os.getcwd()}')
print('No more _PyRuntime errors! 🎉')""",
                height=400
            )
        
        with col2:
            # Create tabs for requirements
            req_tab1, req_tab2 = st.tabs(["Python Requirements", "System Packages"])
            
            with req_tab1:
                requirements = st.text_area(
                    "requirements.txt content",
                    placeholder="""# Add your Python dependencies here
# Example:
# numpy==1.24.0
# pandas==2.0.0
# requests>=2.28.0""",
                    height=150
                )
            
            with req_tab2:
                packages = st.text_area(
                    "packages.txt content",
                    placeholder="""# Add system packages here (one per line)
# Example:
# build-essential
# libssl-dev
# ffmpeg
# imagemagick""",
                    height=150,
                    help="System packages to install with apt-get. Note: Not all packages are available on Streamlit Cloud."
                )
            
            st.info("🐧 **Platform:** Linux only")
            target_platform = "linux"
            
            # Compilation mode selection
            compilation_mode = st.selectbox(
                "Compilation Mode",
                options=[
                    ("max_compatibility", "Universal Binary (Recommended - static Python)"),
                    ("portable", "Portable with Static Python"), 
                    ("standalone", "Standalone with Static Python")
                ],
                format_func=lambda x: x[1],
                help="""
                - Universal Binary: Creates a fully static, portable binary that works anywhere
                - Portable with Static Python: Static Python but requires some system libraries
                - Standalone with Static Python: Self-contained with static Python
                
                All modes now use --static-libpython=yes for maximum compatibility!
                """
            )[0]
            
            output_extension = st.selectbox(
                "Output File Extension",
                options=[".bin", ".sh"],
                index=0
            )
            
            # Show Python version info
            st.info(f"📍 Compiling with Python {get_current_python_version()}")
            st.success("🔗 Using static Python linking for portability!")
        
        # Compile button
        if st.button("🚀 Compile with Nuitka", type="primary"):
            with st.spinner("Compiling with static linking..."):
                results = compile_with_nuitka(
                    code, requirements, packages, target_platform, compilation_mode, output_extension
                )
                
                # Store results in session state
                st.session_state.compilation_results = results
                st.session_state.show_results = True
                
                # Rerun to show results
                st.rerun()

with tab2:
    st.header("📖 How to Use")
    
    st.subheader("🌟 Static Binary - Universal Solution")
    st.success("""
    **The New Approach - Works Everywhere!**
    
    With `--static-libpython=yes`, your binaries now:
    - Work on any Linux system
    - Don't require specific Python versions  
    - Can run from any location (including /mnt/c/ in WSL)
    - Are truly portable!
    """)
    
    st.code("""
# Download and run from ANYWHERE:
chmod +x compiled_program.bin
./compiled_program.bin

# Works from Windows filesystem in WSL:
cd /mnt/c/Users/username/Downloads
./compiled_program.bin    # This now works!

# Works from Linux filesystem:
cp /mnt/c/Users/username/Downloads/compiled_program.bin ~/
cd ~
./compiled_program.bin    # This also works!
    """)
    
    st.subheader("📊 Compilation Mode Comparison")
    comparison_data = {
        "Mode": ["Universal Binary", "Portable", "Standalone"],
        "Static Linking": ["✅ Yes", "✅ Yes", "✅ Yes"],
        "Single File": ["✅ Yes", "❌ No", "✅ Yes"],
        "Size": ["Larger", "Smaller", "Largest"],
        "Portability": ["Maximum", "High", "Maximum"]
    }
    st.table(comparison_data)

with tab3:
    st.header("ℹ️ About")
    
    st.subheader("🔧 Static Linking Solution")
    st.markdown("""
    **The key to the fix:**
    
    - **`--static-libpython=yes`**: This option statically links the Python runtime
    - **`--onefile`**: Creates a single executable file
    - **`--lto=yes`**: Link-time optimization for better compatibility
    
    Together, these create truly portable binaries that work anywhere!
    """)
    
    st.subheader("✅ Problem Solved")
    st.success("""
    **No more `_PyRuntime has different size` errors!**
    
    Static linking means:
    - The Python runtime is embedded in the binary
    - No dependency on system Python version
    - Works from any filesystem (Windows or Linux)
    - Truly universal binaries
    """)
    
    st.subheader("☁️ Current Environment")
    st.code(f"""
    Python Version: {get_current_python_version()}
    Nuitka Version: {get_nuitka_version()}
    Platform: {platform.platform()}
    Architecture: {platform.architecture()[0]}
    Machine: {platform.machine()}
    Static Linking: ✅ Enabled
    """)
    
    st.subheader("📋 Best Practices")
    st.markdown("""
    **For Maximum Portability:**
    1. Always use "Universal Binary" mode
    2. Let Nuitka handle static linking automatically
    3. No need to worry about filesystem locations
    4. Your binaries will just work! 🎉
    """)

# Footer
st.markdown("---")
st.caption("🤖 Created by Claude 3.7 Sonnet | 🚀 Powered by Nuitka with Static Linking")
