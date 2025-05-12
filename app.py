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

def compile_with_nuitka(code, requirements, packages, target_platform, output_extension=".bin"):
    """Compile Python code with Nuitka"""
    # Create status container with expanded height
    status = st.empty()
    status_container = st.container()
    status_container.info("Starting compilation process...")
    
    # Check dependencies first
    missing_deps = check_dependencies()
    if missing_deps:
        error_msg = f"Required dependencies are missing: {', '.join(missing_deps)}\n"
        error_msg += "On Streamlit Cloud, these dependencies are not available, so standalone compilation is not possible.\n"
        error_msg += "Consider using a different deployment platform with full Linux environment support."
        status_container.error(error_msg)
        return "Missing dependencies", error_msg, None, None
    
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
    - Python Version: {sys.version}
    - Platform: {platform.platform()}
    - Architecture: {platform.architecture()}
    - Machine: {platform.machine()}
    - Target Platform: {target_platform}
    """
    status_container.info(system_info)
    
    # Handle Windows compilation - not supported on Streamlit Cloud
    if target_platform == "windows":
        status_container.error("Windows compilation is not supported on Streamlit Cloud. Please use Linux compilation instead.")
        return "Windows compilation not supported", "Windows compilation is not available on Streamlit Cloud due to the lack of Wine support.", None, None
    
    # Handle system packages - not supported on Streamlit Cloud
    if packages.strip():
        status_container.warning("System package installation is not supported on Streamlit Cloud. These packages will be ignored.")
    
    # Write code to a Python file
    script_path = os.path.join(job_dir, "user_script.py")
    with open(script_path, "w") as f:
        f.write(code)
    
    # If requirements provided, write them to requirements.txt
    install_result = "No Python requirements specified."
    if requirements.strip():
        req_path = os.path.join(job_dir, "requirements.txt")
        with open(req_path, "w") as f:
            f.write(requirements)
        
        # Install requirements
        try:
            status_container.info("Installing Python requirements...")
            install_process = subprocess.Popen(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Show installation progress in real-time
            install_output = ""
            for line in iter(install_process.stdout.readline, ''):
                install_output += line
                status_container.text(f"Python requirements installation:\n{install_output}")
                
            install_process.wait()
            
            if install_process.returncode == 0:
                status_container.success("Python requirements installed successfully.")
            else:
                status_container.warning("Python requirements installation completed with warnings.")
            
            install_result = f"Python requirements installation completed with return code: {install_process.returncode}"
            status_container.info(f"{install_result}\n\nStarting compilation...")
        except Exception as e:
            install_result = f"Error installing Python requirements: {str(e)}"
            status_container.error(install_result)
            return install_result, "", None, None
    
    # Continue with Linux compilation
    try:
        # Define the output filename with chosen extension
        output_filename = f"user_script{output_extension}"
        
        # Try different compilation modes in order of preference
        # First, try with onefile (if patchelf is available)
        # Then try without onefile
        compile_attempts = [
            {
                "name": "Standalone Onefile",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--onefile",
                    "--show-progress",
                    "--show-modules",
                    script_path,
                    f"--output-filename={output_filename}",
                    f"--output-dir={output_dir}"
                ]
            },
            {
                "name": "Non-standalone",
                "cmd": [
                    sys.executable, "-m", "nuitka",
                    "--show-progress",
                    "--show-modules",
                    script_path,
                    f"--output-filename={output_filename}",
                    f"--output-dir={output_dir}"
                ]
            }
        ]
        
        for attempt in compile_attempts:
            status_container.info(f"Attempting {attempt['name']} compilation...")
            status_container.info(f"Command: {' '.join(attempt['cmd'])}")
            
            # Start the process 
            process = subprocess.Popen(
                attempt['cmd'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Create a progress bar
            progress_bar = st.progress(0)
            
            # Collect output with progress tracking
            compile_output = ""
            output_buffer = []
            line_count = 0
            total_lines_estimate = 500  # Rough estimate
            
            # Display compilation progress in real-time
            for line in iter(process.stdout.readline, ''):
                compile_output += line
                output_buffer.append(line)
                line_count += 1
                
                # Only keep the last 20 lines for display
                if len(output_buffer) > 20:
                    output_buffer.pop(0)
                
                # Estimate progress
                progress = min(line_count / total_lines_estimate, 0.99)
                progress_bar.progress(progress)
                
                # Update status with recent output
                status_container.text(f"Compilation in progress ({attempt['name']})...\n\n{''.join(output_buffer)}")
            
            # Complete the progress bar
            progress_bar.progress(1.0)
            
            # Process has finished
            process.wait()
            
            status_container.info(f"Compilation finished with exit code: {process.returncode}")
            
            # The binary path
            binary_path = os.path.join(output_dir, output_filename)
            
            # Check if compilation was successful
            if process.returncode == 0 and os.path.exists(binary_path):
                # Execute file command to determine the type of the generated binary
                file_process = subprocess.run(
                    ["file", binary_path],
                    capture_output=True,
                    text=True
                )
                binary_info = file_process.stdout
                status_container.info(f"Binary information: {binary_info}")
                
                # Make the binary executable
                os.chmod(binary_path, 0o755)
                
                # Fix line endings for shell scripts
                if binary_path.endswith(".sh"):
                    fix_line_endings(binary_path)
                
                status_container.success(f"Compilation complete ({attempt['name']})! You can download the executable now.")
                
                # Return the binary directly
                return install_result, compile_output, binary_path, binary_info
            else:
                status_container.warning(f"{attempt['name']} compilation failed, trying next method...")
                continue
        
        # If we get here, all attempts failed
        status_container.error("All compilation attempts failed. Could not find executable file.")
        return install_result, f"{compile_output}\n\nAll compilation attempts failed. See output for details.", None, "Binary compilation failed."
        
    except Exception as e:
        status_container.error(f"Error during compilation: {str(e)}")
        return install_result, f"Error during compilation: {str(e)}", None, "Binary compilation failed."

# App title and description
st.title("🚀 Nuitka Python Compiler (Streamlit Cloud)")
st.markdown("""
This tool compiles your Python code into a single executable file using Nuitka.
**Note:** This version only supports Linux compilation due to Streamlit Cloud limitations.
""")

# Check for missing dependencies at startup
missing_deps = check_dependencies()
if missing_deps:
    st.error(f"""
    ⚠️ **Missing Dependencies:** {', '.join(missing_deps)}
    
    Streamlit Cloud doesn't include all required system packages for Nuitka compilation.
    You may still be able to compile using non-standalone mode, but standalone executables require these packages.
    """)

# Create tabs for different sections
tab1, tab2, tab3 = st.tabs(["Compiler", "How to Use", "About"])

with tab1:
    # Create columns for code and requirements
    col1, col2 = st.columns([2, 1])
    
    with col1:
        code = st.text_area(
            "Your Python Code",
            value="# Enter your Python code here\n\nprint('Hello from compiled Python!')\nprint('This is running as a native executable')\n\n# This code will be compiled into an executable",
            height=300
        )
    
    with col2:
        # Create tabs for requirements and packages
        req_tab1, req_tab2 = st.tabs(["Python Requirements", "System Packages"])
        
        with req_tab1:
            requirements = st.text_area(
                "requirements.txt",
                placeholder="numpy==1.24.0\npandas==2.0.0\n# Add your Python dependencies here",
                height=230
            )
        
        with req_tab2:
            packages = st.text_area(
                "packages.txt",
                placeholder="# System packages are not supported on Streamlit Cloud\n# This field is disabled",
                height=230,
                disabled=True,
                help="System package installation is not available on Streamlit Cloud"
            )
        
        # Target platform selection (Linux only)
        st.info("🔓 **Platform:** Linux only (Windows compilation not available on Streamlit Cloud)")
        target_platform = "linux"
        
        # Extension options
        output_extension = st.selectbox(
            "Output File Extension",
            options=[".bin", ".sh"], 
            index=0,
            help="Choose the file extension for the compiled Linux executable."
        )
    
    # Compile button
    if st.button("Compile with Nuitka", type="primary"):
        install_result, compile_output, binary_path, binary_info = compile_with_nuitka(code, requirements, packages, target_platform, output_extension)
        
        # Display compilation details in an expander
        with st.expander("Compilation Details", expanded=True):
            st.subheader("Requirements Installation")
            st.text(install_result)
            
            st.subheader("Compilation Log")
            st.text(compile_output)
            
            if binary_info:
                st.subheader("Binary Information")
                st.text(binary_info)
        
        # Download section
        if binary_path and os.path.exists(binary_path):
            st.success("✅ Compilation successful!")
            
            # Determine filename for download
            download_filename = f"compiled_program{output_extension}"
            
            # Create download button
            with open(binary_path, "rb") as f:
                st.download_button(
                    label=f"Download Compiled Program ({os.path.basename(binary_path)})", 
                    data=f, 
                    file_name=download_filename,
                    mime="application/octet-stream"
                )
            
            # Show Linux instructions
            st.info(f"""
            **To run on Linux:**
            1. Save the file to your computer
            2. Open a terminal in the directory where you saved it
            3. Make it executable: `chmod +x {download_filename}`
            4. Run it: `./{download_filename}`
            
            **To run on Windows with WSL:**
            1. Install WSL (Windows Subsystem for Linux)
            2. Copy the file to your WSL environment (not the Windows file system)
            3. Make it executable: `chmod +x {download_filename}`
            4. Run it: `./{download_filename}`
            """)
            
            # Run the binary directly
            st.subheader("Test Run")
            if st.button("Run Compiled Binary"):
                st.write("Running the compiled binary... (output will appear below)")
                with st.spinner("Executing..."):
                    success, result = run_compiled_binary(binary_path)
                    
                    if success:
                        st.success("Binary executed successfully!")
                    else:
                        st.warning("Binary execution encountered issues.")
                    
                    st.text_area("Execution Output", result, height=300)
        else:
            st.error("❌ Compilation failed or file creation failed.")

with tab2:
    st.header("How to Use the Compiled Binary")
    
    st.subheader("Linux Executables (.bin/.sh)")
    st.markdown("""
    1. Download the compiled executable (.bin or .sh)
    2. Open a terminal in the directory where you saved it
    3. Make the file executable: `chmod +x your_program.bin`
    4. Run the program: `./your_program.bin`
    """)
    
    st.subheader("WSL Instructions for Linux Executables")
    st.markdown("""
    If you're trying to run Linux executables on Windows:
    
    1. Install WSL from Microsoft Store
    2. Open WSL
    3. Copy the file to a native WSL directory (not inside /mnt/c/)
    4. Make it executable: `chmod +x your_program.bin`
    5. Run it: `./your_program.bin`
    
    If you get "cannot execute binary file" error:
    - Make sure you're running it with `./your_program.bin`
    - Try fixing line endings: `dos2unix your_program.bin`
    - Make sure you're running it from a Linux environment, not Windows cmd/PowerShell
    """)
    
    st.subheader("About Onefile Mode")
    st.markdown("""
    This tool uses Nuitka's "onefile" mode which:
    
    1. Creates a single standalone executable
    2. Contains all dependencies in one file
    3. Unpacks necessary files to a temporary directory at runtime
    4. Cleans up after execution
    
    This makes distribution simple - just share this one file!
    
    **Note:** On Streamlit Cloud, standalone mode may not work due to missing system dependencies.
    """)

with tab3:
    st.header("About Nuitka")
    st.markdown("""
    Nuitka is a Python compiler that converts Python code to C/C++ code, which is then compiled to a native executable.
    
    **Benefits of using Nuitka:**
    - Improved performance
    - Protection of source code
    - Standalone applications (no Python required on the target machine)
    - Reduced startup time
    
    **Technical Details:**
    - This tool compiles for Linux platforms only (on Streamlit Cloud)
    - Linux binaries are 64-bit ELF format
    """)
    
    st.header("About This Tool")
    st.markdown("""
    This tool provides a simple web interface for compiling Python code with Nuitka in onefile mode.
    
    **Features (Streamlit Cloud version):**
    - Compiles to single executable files (.bin or .sh)
    - Linux compilation only
    - Includes all Python dependencies 
    - Real-time progress tracking
    - Test execution of compiled binaries
    - Fallback to non-standalone mode if dependencies are missing
    
    **Limitations:**
    - Only Linux compilation is supported
    - System packages cannot be installed
    - Windows compilation is not available
    - Some system dependencies (like patchelf) may be missing
    - Some advanced Nuitka features may not be supported
    
    **Note:** For Windows compilation support and full system dependency availability, consider using the Docker/Hugging Face Spaces version of this tool.
    """)
    
    # Dependency status
    st.subheader("System Dependencies Status")
    missing_deps = check_dependencies()
    if missing_deps:
        st.error(f"Missing dependencies: {', '.join(missing_deps)}")
        st.markdown("""
        **Impact:**
        - Standalone compilation may fail
        - Non-standalone compilation should still work
        - Executables may require Python runtime on target system
        """)
    else:
        st.success("All required dependencies are available!")

# Footer
st.markdown("---")
st.caption("Created by Claude 3.7 Sonnet | Nuitka is a Python compiler that converts your Python code to native executables")
