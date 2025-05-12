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

def fix_line_endings(file_path):
    """Fix line endings to ensure Linux compatibility"""
    try:
        # Try to use dos2unix if available
        result = subprocess.run(["which", "dos2unix"], capture_output=True)
        if result.returncode == 0:
            subprocess.run(["dos2unix", file_path], check=True, capture_output=True)
            return True
        else:
            # Fallback: manually fix line endings
            with open(file_path, 'rb') as f:
                content = f.read()
            content = content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
            with open(file_path, 'wb') as f:
                f.write(content)
            return True
    except Exception as e:
        st.warning(f"Could not fix line endings: {str(e)}")
        return False

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

def run_compiled_binary(binary_path):
    """Run the compiled binary and return the output"""
    try:
        # Skip execution for Windows binaries
        if binary_path.endswith(".exe"):
            return False, "Windows executables (.exe) cannot be run in this Linux environment."
        
        # Make the binary executable
        os.chmod(binary_path, 0o755)
        
        # Fix line endings for shell scripts
        if binary_path.endswith(".sh"):
            fix_line_endings(binary_path)
        
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
                    install_log += f"   Error: {install_process.stderr}\n"
        
        if successful_packages:
            status_container.success(f"Successfully installed {len(successful_packages)} packages")
        
        if failed_packages:
            status_container.warning(f"Failed to install {len(failed_packages)} packages. This may cause compilation issues.")
        
        summary = f"""
System Packages Summary:
✅ Successful: {', '.join(successful_packages)}
❌ Failed: {', '.join(failed_packages)}

Note: On Streamlit Cloud, some packages may not be available or may require different installation methods.
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

def format_compilation_log(log_text):
    """Format compilation log for better readability"""
    lines = log_text.splitlines()
    formatted_lines = []
    
    for line in lines:
        # Skip very repetitive lines
        if "Setting 'RPATH' value" in line:
            # Only show first few RPATH messages
            if len([l for l in formatted_lines if "Setting 'RPATH'" in l]) < 3:
                formatted_lines.append("  " + line)
            elif len([l for l in formatted_lines if "Setting 'RPATH'" in l]) == 3:
                formatted_lines.append("  ... (setting RPATH for multiple shared libraries)")
        elif line.startswith("Nuitka"):
            formatted_lines.append("✓ " + line)
        elif "error" in line.lower() or "failed" in line.lower():
            formatted_lines.append("❌ " + line)
        elif "success" in line.lower():
            formatted_lines.append("✅ " + line)
        else:
            formatted_lines.append("  " + line)
    
    return "\n".join(formatted_lines[-50:])  # Only show last 50 lines

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

def get_system_info():
    """Get detailed system information for troubleshooting"""
    info = {
        "Python Version": sys.version,
        "Platform": platform.platform(),
        "Architecture": platform.architecture(),
        "Machine": platform.machine(),
        "Processor": platform.processor() or "Unknown",
        "Python Path": sys.executable,
        "Environment": "Streamlit Cloud" if "streamlit_app" in os.getcwd() else "Local/Other"
    }
    return info

def compile_with_nuitka(code, requirements, packages, target_platform, output_extension=".bin"):
    """Compile Python code with Nuitka"""
    # Create status container
    status_container = st.container()
    status_container.info("Starting compilation process...")
    
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
    
    # Log system info
    system_info = get_system_info()
    info_text = "\n".join([f"- {k}: {v}" for k, v in system_info.items()])
    status_container.info(f"System Information:\n{info_text}")
    
    # Handle Windows compilation
    if target_platform == "windows":
        error_msg = """
        ⚠️ **Windows compilation is not supported on Streamlit Cloud**
        
        Reason: Windows compilation requires Wine (Windows compatibility layer), which is not available on Streamlit Cloud.
        
        **Alternatives:**
        1. Use the Linux compilation option below
        2. Use the Docker/Hugging Face Spaces version for Windows compilation support
        3. Compile locally on a Windows machine or Windows VM
        """
        status_container.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'install_result': "Windows compilation not supported",
            'compile_output': "Windows compilation is not available on Streamlit Cloud due to the lack of Wine support.",
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
        
        # Compilation attempts with different modes for better compatibility
        compile_attempts = [
            {
                "name": "Standalone (Recommended for distribution)",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--show-progress",
                    "--remove-output",
                    "--python-flag=no_site",  # More portable
                    script_path,
                    f"--output-dir={output_dir}"
                ]
            },
            {
                "name": "Non-standalone (Better compatibility)",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--show-progress", 
                    "--remove-output",
                    "--python-flag=no_site",
                    script_path,
                    f"--output-dir={output_dir}"
                ]
            }
        ]
        
        for attempt in compile_attempts:
            status_container.info(f"Attempting {attempt['name']} compilation...")
            
            # Show command in collapsible section
            with status_container.expander(f"Command for {attempt['name']}"):
                st.code(' '.join(attempt['cmd']))
            
            # Run compilation
            process = subprocess.Popen(
                attempt['cmd'],
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
                
                # Show formatted log
                formatted_log = format_compilation_log(compile_output)
                with log_placeholder.container():
                    with st.expander("📋 Compilation Log", expanded=False):
                        st.text(formatted_log)
            
            progress_bar.progress(1.0)
            process.wait()
            
            status_container.info(f"Compilation finished with exit code: {process.returncode}")
            
            # Find the compiled binary
            output_filename = f"user_script{output_extension}"
            binary_path = find_compiled_binary(output_dir, output_filename)
            
            if process.returncode == 0 and binary_path:
                # Get binary info
                file_process = subprocess.run(["file", binary_path], capture_output=True, text=True)
                binary_info = file_process.stdout
                
                # Make executable
                os.chmod(binary_path, 0o755)
                
                # Add system info to result
                result_summary = f"""
Compilation Details:
- Mode: {attempt['name']}
- Exit Code: {process.returncode}
- Output Path: {binary_path}
- File Size: {os.path.getsize(binary_path) / 1024 / 1024:.2f} MB

System Packages: {packages_result}
Python Requirements: {install_result}

Binary Information: {binary_info}

Note: If you encounter runtime errors like '_PyRuntime has different size', 
this is usually due to Python version mismatches between compilation and runtime environments.
Try running in an environment with Python {sys.version.split()[0]}.
"""
                
                status_container.success(f"✅ {attempt['name']} compilation successful!")
                return {
                    'success': True,
                    'install_result': result_summary,
                    'compile_output': compile_output,
                    'binary_path': binary_path,
                    'binary_info': binary_info,
                    'output_extension': output_extension
                }
            else:
                status_container.warning(f"⚠️ {attempt['name']} compilation failed")
                if attempt == compile_attempts[-1]:  # Last attempt
                    return {
                        'success': False,
                        'error': "All compilation attempts failed",
                        'install_result': f"All compilation attempts failed.\n\nSystem Packages: {packages_result}\nPython Requirements: {install_result}",
                        'compile_output': compile_output,
                        'binary_path': None,
                        'binary_info': "All compilation attempts failed"
                    }
                continue
        
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

# App title and description
st.title("🚀 Nuitka Python Compiler (Streamlit Cloud)")
st.markdown("""
Convert your Python code into optimized executables using Nuitka.
**Linux compilation only** (Wine not available on Streamlit Cloud).
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
            
            # Stats
            if results['binary_path'] and os.path.exists(results['binary_path']):
                file_size = os.path.getsize(results['binary_path'])
                st.metric("File Size", f"{file_size / 1024 / 1024:.2f} MB")
                
                # Download
                download_filename = f"compiled_program{results.get('output_extension', '.bin')}"
                with open(results['binary_path'], "rb") as f:
                    st.download_button(
                        "⬇️ Download Compiled Program",
                        data=f,
                        file_name=download_filename,
                        mime="application/octet-stream",
                        type="primary"
                    )
                
                # Binary info with troubleshooting tips
                with st.expander("🔍 Binary Information & Troubleshooting"):
                    st.text(results['binary_info'])
                    st.markdown("""
                    **If you encounter runtime errors:**
                    
                    1. **`_PyRuntime has different size` error:**
                       - This happens when Python versions differ between compilation and runtime
                       - Try running on a system with Python 3.12.x (same as Streamlit Cloud)
                       - Use non-standalone mode for better compatibility
                    
                    2. **Segmentation fault:**
                       - Usually caused by Python version mismatches
                       - Try copying the binary to a native WSL directory (not /mnt/c/)
                       - Ensure you're running in a proper Linux environment
                    
                    3. **File not found errors:**
                       - Make sure the binary is executable: `chmod +x compiled_program.bin`
                       - Check if you're in the correct directory
                    """)
                
                # Test run
                st.subheader("🧪 Test Run (on Streamlit Cloud)")
                st.warning("Note: Testing on Streamlit Cloud may not reflect behavior on your local system")
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
print('This is running as a native executable')

# For packages that need special handling during compilation:
# - Use explicit imports instead of dynamic imports
# - Avoid importing with sudo/elevated privileges
# - Use standard library when possible""",
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
                    height=200
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
                    height=200,
                    help="System packages to install with apt-get. Note: Not all packages are available on Streamlit Cloud."
                )
            
            st.info("🐧 **Platform:** Linux only")
            target_platform = "linux"
            
            output_extension = st.selectbox(
                "Output File Extension",
                options=[".bin", ".sh"],
                index=0
            )
            
            # Tips for packaging
            with st.expander("💡 Tips for Better Packaging"):
                st.markdown("""
                **For successful compilation:**
                - Use explicit imports: `import module` instead of dynamic imports
                - Test with minimal dependencies first
                - Some packages work better in non-standalone mode
                
                **System Packages:**
                - Only basic Debian packages are available
                - Some packages may fail to install on Streamlit Cloud
                - Failed packages won't prevent compilation from proceeding
                
                **Runtime Compatibility:**
                - Binaries compiled on Streamlit Cloud work best on similar Ubuntu/Debian systems
                - For WSL compatibility, ensure similar Python versions
                - Use non-standalone mode for better cross-system compatibility
                """)
        
        # Compile button
        if st.button("🚀 Compile with Nuitka", type="primary"):
            with st.spinner("Compiling..."):
                results = compile_with_nuitka(
                    code, requirements, packages, target_platform, output_extension
                )
                
                # Store results in session state
                st.session_state.compilation_results = results
                st.session_state.show_results = True
                
                # Rerun to show results
                st.rerun()

with tab2:
    st.header("📖 How to Use")
    
    st.subheader("🐧 Linux Executables")
    st.code("""
# Download the file
# In terminal:
chmod +x compiled_program.bin
./compiled_program.bin
    """)
    
    st.subheader("🪟 Windows WSL")
    st.markdown("""
    1. Install Windows Subsystem for Linux (WSL)
    2. **Important:** Copy file to WSL filesystem, not /mnt/c/
    ```bash
    # Good: Copy to WSL home directory
    cp /mnt/c/Users/username/Downloads/compiled_program.bin ~/
    cd ~
    chmod +x compiled_program.bin
    ./compiled_program.bin
    
    # Bad: Running from Windows filesystem
    cd /mnt/c/Users/username/Downloads/
    ./compiled_program.bin  # May cause errors
    ```
    """)
    
    st.subheader("⚙️ Compilation Modes")
    st.markdown("""
    **Standalone Mode:**
    - ✅ Self-contained executable
    - ✅ No Python required on target system
    - ❌ Larger file size
    - ❌ May have compatibility issues across different Linux versions
    
    **Non-standalone Mode:**
    - ✅ Smaller file size
    - ✅ Better cross-system compatibility
    - ✅ More likely to run on different Python versions
    - ❌ Requires Python on target system
    """)
    
    st.subheader("🔧 System Packages")
    st.markdown("""
    **Supported packages:**
    - Most standard Debian packages from the bullseye repository
    - Build tools: `build-essential`, `gcc`, `g++`
    - Libraries: `libssl-dev`, `libffi-dev`, `libxml2-dev`
    - Tools: `ffmpeg`, `imagemagick` (basic versions)
    
    **Limitations:**
    - Some packages may not be available
    - Complex packages requiring configuration may fail
    - No GUI-related packages in headless environment
    """)

with tab3:
    st.header("ℹ️ About")
    
    st.subheader("🔧 Nuitka Compiler")
    st.markdown("""
    Nuitka converts Python to optimized C++ code, then compiles to native executables.
    
    **Benefits:**
    - 🚀 Faster execution
    - 🔒 Source code protection
    - 📦 Single-file distribution
    - ⚡ Reduced startup time
    """)
    
    st.subheader("☁️ Streamlit Cloud Environment")
    system_info = get_system_info()
    st.markdown("**Current Environment:**")
    for key, value in system_info.items():
        if key == "Python Version":
            st.text(f"{key}: {value.split()[0]}")
        else:
            st.text(f"{key}: {value}")
    
    st.subheader("⚠️ Known Issues & Solutions")
    st.markdown("""
    **Common Runtime Errors:**
    
    1. **`_PyRuntime has different size in shared object`**
       - **Cause:** Python version mismatch between compilation and runtime
       - **Solution:** Use systems with similar Python versions (3.12.x)
    
    2. **Segmentation fault on WSL**
       - **Cause:** Running binary from Windows filesystem (/mnt/c/)
       - **Solution:** Copy binary to native WSL filesystem
    
    3. **Binary won't execute**
       - **Cause:** Missing execute permissions
       - **Solution:** `chmod +x compiled_program.bin`
    
    **Recommendations:**
    - Use non-standalone mode for better compatibility
    - Test on similar Ubuntu/Debian systems
    - Keep Python versions consistent between compilation and runtime
    """)
    
    st.subheader("🔧 Current Status")
    env_status = {
        "Dependencies": "✅ Available" if not missing_deps else f"❌ Missing: {', '.join(missing_deps)}",
        "Platform": "Linux (Streamlit Cloud)",
        "Python": sys.version.split()[0],
        "Nuitka": "✅ Installed"
    }
    
    for key, value in env_status.items():
        st.text(f"{key}: {value}")

# Footer
st.markdown("---")
st.caption("🤖 Created by Claude 3.7 Sonnet | 🚀 Powered by Nuitka")
