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

def compile_with_nuitka(code, requirements, target_platform, output_extension=".bin"):
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
    system_info = f"""
    System Information:
    - Python: {sys.version.split()[0]}
    - Platform: {platform.platform()}
    - Architecture: {platform.architecture()[0]}
    - Target: {target_platform}
    """
    status_container.info(system_info)
    
    # Handle Windows compilation
    if target_platform == "windows":
        status_container.error("""
        ⚠️ **Windows compilation is not supported on Streamlit Cloud**
        
        Reason: Windows compilation requires Wine (Windows compatibility layer), which is not available on Streamlit Cloud.
        
        **Alternatives:**
        1. Use the Linux compilation option below
        2. Use the Docker/Hugging Face Spaces version for Windows compilation support
        3. Compile locally on a Windows machine or Windows VM
        """)
        return "Windows compilation not supported", "Windows compilation is not available on Streamlit Cloud due to the lack of Wine support.", None, None
    
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
            else:
                status_container.warning("⚠️ Python requirements installation completed with warnings.")
            
            install_result = f"Return code: {install_process.returncode}"
        except Exception as e:
            install_result = f"Error: {str(e)}"
            status_container.error(install_result)
            return install_result, "", None, None
    
    # Compilation
    try:
        status_container.info("🔧 Starting compilation...")
        
        # Try standalone first, then fallback to non-standalone
        compile_attempts = [
            {
                "name": "Standalone",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--show-progress",
                    "--remove-output",
                    script_path,
                    f"--output-dir={output_dir}"
                ]
            },
            {
                "name": "Non-standalone",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--show-progress", 
                    "--remove-output",
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
                
                status_container.success(f"✅ {attempt['name']} compilation successful!")
                return install_result, compile_output, binary_path, binary_info
            else:
                status_container.warning(f"⚠️ {attempt['name']} compilation failed")
                if attempt == compile_attempts[-1]:  # Last attempt
                    return install_result, compile_output, None, "All compilation attempts failed"
                continue
        
    except Exception as e:
        status_container.error(f"❌ Error during compilation: {str(e)}")
        return install_result, f"Error: {str(e)}", None, "Compilation error"

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
        requirements = st.text_area(
            "Python Requirements (requirements.txt)",
            placeholder="""# Add your Python dependencies here
# Example:
# numpy==1.24.0
# pandas==2.0.0
# requests>=2.28.0""",
            height=200
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
            - Avoid packages requiring sudo/root privileges
            - Test with minimal dependencies first
            - Some packages work better in non-standalone mode
            
            **Common issues:**
            - GUI libraries may not work in compiled form
            - Some binary dependencies may be missing
            - Network-dependent code may behave differently
            """)
    
    # Compile button
    if st.button("🚀 Compile with Nuitka", type="primary"):
        with st.spinner("Compiling..."):
            install_result, compile_output, binary_path, binary_info = compile_with_nuitka(
                code, requirements, target_platform, output_extension
            )
        
        # Results section
        if binary_path and os.path.exists(binary_path):
            st.success("🎉 Compilation successful!")
            
            # Stats
            file_size = os.path.getsize(binary_path)
            st.metric("File Size", f"{file_size / 1024 / 1024:.2f} MB")
            
            # Download
            download_filename = f"compiled_program{output_extension}"
            with open(binary_path, "rb") as f:
                st.download_button(
                    "⬇️ Download Compiled Program",
                    data=f,
                    file_name=download_filename,
                    mime="application/octet-stream",
                    type="primary"
                )
            
            # Binary info
            with st.expander("🔍 Binary Information"):
                st.text(binary_info)
            
            # Test run
            st.subheader("🧪 Test Run")
            if st.button("Run Compiled Binary"):
                with st.spinner("Executing..."):
                    success, result = run_compiled_binary(binary_path)
                
                if success:
                    st.success("✅ Execution successful!")
                else:
                    st.warning("⚠️ Execution completed with issues")
                
                st.text_area("Execution Output", result, height=200)
        else:
            st.error("❌ Compilation failed")
        
        # Detailed logs (collapsible)
        with st.expander("📋 Detailed Logs", expanded=False):
            st.subheader("Requirements Installation")
            st.text(install_result)
            
            st.subheader("Compilation Output")
            st.text(compile_output if compile_output else "No output available")

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
    2. Copy file to WSL environment
    3. Make executable and run:
    ```bash
    chmod +x compiled_program.bin
    ./compiled_program.bin
    ```
    """)
    
    st.subheader("⚙️ Compilation Modes")
    st.markdown("""
    **Standalone Mode:**
    - ✅ Self-contained executable
    - ✅ No Python required on target system
    - ❌ Larger file size
    - ❌ May fail if dependencies are missing
    
    **Non-standalone Mode:**
    - ✅ Smaller file size
    - ✅ More likely to compile successfully
    - ❌ Requires Python on target system
    - ❌ Less portable
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
    
    st.subheader("☁️ Streamlit Cloud Limitations")
    st.markdown("""
    **Supported:**
    - ✅ Linux compilation
    - ✅ Python packages via pip
    - ✅ Basic system packages
    
    **Not Supported:**
    - ❌ Windows compilation (no Wine)
    - ❌ Complex system dependencies
    - ❌ GUI applications
    - ❌ Root/sudo operations
    """)
    
    st.subheader("🔧 Current Environment")
    env_info = {
        "Python Version": sys.version.split()[0],
        "Platform": platform.platform(),
        "Architecture": platform.architecture()[0],
        "Dependencies": "✅ Available" if not missing_deps else f"❌ Missing: {', '.join(missing_deps)}"
    }
    
    for key, value in env_info.items():
        st.text(f"{key}: {value}")

# Footer
st.markdown("---")
st.caption("🤖 Created by Claude 3.7 Sonnet | 🚀 Powered by Nuitka")
