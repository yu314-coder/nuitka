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
        subprocess.run(["dos2unix", file_path], check=True, capture_output=True)
        return True
    except Exception as e:
        st.warning(f"Could not fix line endings: {str(e)}")
        return False

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
        
        # Install packages line by line (equivalent to install_packages.sh)
        install_log = ""
        with open(temp_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                status_container.info(f"Installing: {line}")
                process = subprocess.run(
                    ["sudo", "apt-get", "update", "-y"],
                    capture_output=True,
                    text=True
                )
                install_log += f"Update output: {process.stdout}\n{process.stderr}\n"
                
                process = subprocess.run(
                    ["sudo", "apt-get", "install", "-y", line],
                    capture_output=True,
                    text=True
                )
                install_log += f"Install {line}: {process.stdout}\n{process.stderr}\n"
        
        status_container.success("System packages installed successfully.")
        return f"System packages installation:\n{install_log}"
    
    except Exception as e:
        status_container.error(f"Failed to install system packages: {str(e)}")
        return f"Error installing system packages: {str(e)}"
    
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def compile_for_windows(code, output_dir, status_container):
    """Compile Python code for Windows using Wine and MinGW"""
    # Create temporary script file
    fd, script_path = tempfile.mkstemp(suffix='.py')
    try:
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(code)
        
        status_container.info("Starting Windows compilation...")
        
        # Start Xvfb if not running
        xvfb_cmd = ["Xvfb", ":99", "-screen", "0", "1024x768x16"]
        xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        
        # Set environment variables
        env = os.environ.copy()
        env.update({
            "DISPLAY": ":99",
            "WINEPREFIX": "/home/user/.wine",
            "WINEDEBUG": "-all"
        })
        
        output_name = "program.exe"
        compile_output = ""
        
        try:
            # Download Python installer if needed
            python_installer = "/tmp/python-3.9.13-amd64.exe"
            if not os.path.exists(python_installer):
                status_container.info("Downloading Python installer...")
                process = subprocess.run(
                    ["wget", "-q", "-O", python_installer, "https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe"],
                    capture_output=True,
                    text=True
                )
                compile_output += f"Download output: {process.stdout}\n{process.stderr}\n"
            
            # Install Python - will only run if needed
            status_container.info("Installing Python in Wine...")
            process = subprocess.run(
                ["timeout", "180s", "wine", python_installer, "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0"],
                env=env,
                capture_output=True,
                text=True
            )
            compile_output += f"Python install output: {process.stdout}\n{process.stderr}\n"
            
            # Find Python executable
            python_paths = [
                "C:\\users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe",
                "C:\\Python39\\python.exe",
                "C:\\windows\\py.exe"
            ]
            
            python_path = None
            for path in python_paths:
                test_cmd = ["timeout", "30s", "wine", path, "--version"]
                process = subprocess.run(test_cmd, env=env, capture_output=True, text=True)
                if process.returncode == 0:
                    python_path = path
                    status_container.info(f"Found working Python at: {python_path}")
                    break
            
            if not python_path:
                status_container.error("Failed to find working Python installation")
                return False, compile_output, None
            
            # Install Nuitka
            status_container.info("Installing Nuitka in Wine Python...")
            process = subprocess.run(
                ["timeout", "180s", "wine", python_path, "-m", "pip", "install", "nuitka"],
                env=env,
                capture_output=True,
                text=True
            )
            compile_output += f"Nuitka install output: {process.stdout}\n{process.stderr}\n"
            
            # Run compilation
            status_container.info("Compiling with Nuitka...")
            compile_cmd = [
                "timeout", "300s", "wine", python_path, "-m", "nuitka",
                "--mingw64",
                "--onefile",
                "--standalone",
                "--show-progress",
                f"--output-dir={output_dir}",
                f"--output-filename={output_name}",
                script_path
            ]
            
            # Create icon file if it doesn't exist
            icon_path = "/app/icon.ico"
            if os.path.exists(icon_path):
                compile_cmd.insert(-1, f"--windows-icon-from-ico={icon_path}")
            
            process = subprocess.Popen(
                compile_cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Show compilation progress in real-time
            for line in iter(process.stdout.readline, ''):
                compile_output += line
                status_container.text(f"Windows compilation progress:\n{compile_output}")
            
            process.wait()
            
            if process.returncode == 0:
                status_container.success("Windows compilation successful!")
                return True, compile_output, os.path.join(output_dir, output_name)
            else:
                status_container.error("Windows compilation failed.")
                return False, compile_output, None
        
        finally:
            # Clean up Xvfb
            if xvfb_proc:
                xvfb_proc.terminate()
                xvfb_proc.wait()
    
    except Exception as e:
        status_container.error(f"Windows compilation error: {str(e)}")
        return False, str(e), None
    
    finally:
        # Clean up
        if os.path.exists(script_path):
            os.unlink(script_path)

def compile_with_nuitka(code, requirements, packages, target_platform, output_extension=".bin"):
    """Compile Python code with Nuitka without using threads"""
    # Create status container with expanded height
    status = st.empty()
    status_container = st.container()
    status_container.info("Starting compilation process...")
    
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
    
    # Install system packages if specified
    if packages.strip():
        packages_result = install_system_packages(packages, status_container)
        status_container.text(packages_result)
    
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
        
        # Install requirements (only needed for Linux builds)
        if target_platform == "linux":
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
    
    # Handle Windows compilation separately
    if target_platform == "windows":
        success, win_output, win_binary = compile_for_windows(code, output_dir, status_container)
        if success and win_binary:
            # Get binary info
            file_process = subprocess.run(
                ["file", win_binary],
                capture_output=True,
                text=True
            )
            binary_info = file_process.stdout
            
            return install_result, win_output, win_binary, binary_info
        else:
            return install_result, win_output, None, "Windows binary compilation failed."
    
    # Continue with Linux compilation
    try:
        # Define the output filename with chosen extension
        output_filename = f"user_script{output_extension}"
        
        # Use the exact command format provided, adapted to our variables
        compile_cmd = [
            sys.executable, "-m", "nuitka",
            "--onefile",
            "--show-progress",
            "--show-modules",
            script_path,
            f"--output-filename={output_filename}",
            f"--output-dir={output_dir}"
        ]
        
        status_container.info(f"Starting compilation with command:\n{' '.join(compile_cmd)}")
        
        # Start the process 
        process = subprocess.Popen(
            compile_cmd,
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
            status_container.text(f"Compilation in progress...\n\n{''.join(output_buffer)}")
        
        # Complete the progress bar
        progress_bar.progress(1.0)
        
        # Process has finished
        process.wait()
        
        status_container.info(f"Compilation finished with exit code: {process.returncode}")
        
        # The binary path
        binary_path = os.path.join(output_dir, output_filename)
        
        # Execute file command to determine the type of the generated binary
        binary_info = "Binary file not found."
        if os.path.exists(binary_path):
            file_process = subprocess.run(
                ["file", binary_path],
                capture_output=True,
                text=True
            )
            binary_info = file_process.stdout
            status_container.info(f"Binary information: {binary_info}")
        else:
            status_container.error(binary_info)
        
        # Check if compilation was successful
        if os.path.exists(binary_path):
            # Make the binary executable
            os.chmod(binary_path, 0o755)
            
            # Fix line endings for shell scripts
            if binary_path.endswith(".sh"):
                fix_line_endings(binary_path)
            
            status_container.success("Compilation complete! You can download the executable now.")
            
            # Return the binary directly
            return install_result, compile_output, binary_path, binary_info
        else:
            status_container.error("Compilation failed. Could not find executable file.")
            return install_result, f"{compile_output}\n\nCompilation failed. See output for details.", None, binary_info
    except Exception as e:
        status_container.error(f"Error during compilation: {str(e)}")
        return install_result, f"Error during compilation: {str(e)}", None, "Binary compilation failed."

# App title and description
st.title("🚀 Nuitka Python Compiler")
st.markdown("""
This tool compiles your Python code into a single executable file using Nuitka.
You can compile for Linux or Windows platforms.
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
                placeholder="# Add system packages that require apt-get install\nlibssl-dev\nlibffi-dev",
                height=230,
                help="These packages will be installed using sudo apt-get install"
            )
        
        # Target platform selection
        target_platform = st.radio(
            "Target Platform",
            options=["linux", "windows"],
            index=0,
            help="Select the platform for which to compile the executable."
        )
        
        # Extension options (only show for Linux)
        if target_platform == "linux":
            output_extension = st.selectbox(
                "Output File Extension",
                options=[".bin", ".sh"], 
                index=0,
                help="Choose the file extension for the compiled Linux executable."
            )
        else:
            output_extension = ".exe"  # For Windows, always use .exe
    
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
            
            # Determine filename for download based on target platform
            if target_platform == "linux":
                download_filename = f"compiled_program{output_extension}"
            else:
                download_filename = "compiled_program.exe"
            
            # Create download button
            with open(binary_path, "rb") as f:
                st.download_button(
                    label=f"Download Compiled Program ({os.path.basename(binary_path)})", 
                    data=f, 
                    file_name=download_filename,
                    mime="application/octet-stream"
                )
            
            # Show appropriate instructions based on target platform
            if target_platform == "linux":
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
            else:
                st.info(f"""
                **To run on Windows:**
                1. Save the .exe file to your computer
                2. Double-click the file to run it
                
                **Note:** This is a Windows executable and will only run on Windows systems.
                """)
            
            # Run the binary directly (only for Linux builds)
            if target_platform == "linux":
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
                st.warning("Windows executables cannot be test-run in this environment. Please download and run on a Windows system.")
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
    
    st.subheader("Windows Executables (.exe)")
    st.markdown("""
    1. Download the compiled .exe file
    2. Double-click to run it on any Windows system
    
    **Note:** The Windows executable is cross-compiled using Wine and MinGW. While this should work for most simple Python scripts, complex applications might have issues.
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
    - This tool can compile for both Linux and Windows platforms
    - Linux binaries are 64-bit ELF format
    - Windows binaries are 64-bit PE format (.exe)
    - Windows compilation uses cross-compilation via Wine and MinGW
    """)
    
    st.header("About This Tool")
    st.markdown("""
    This tool provides a simple web interface for compiling Python code with Nuitka in onefile mode.
    
    **Features:**
    - Compiles to single executable files (.bin, .sh, or .exe)
    - Cross-platform compilation (Linux and Windows)
    - Includes all dependencies 
    - Supports system packages via packages.txt
    - Real-time progress tracking
    
    **Limitations:**
    - Windows executables are cross-compiled and may not work with complex dependencies
    - Very large projects might time out in the Hugging Face Space environment
    - Some advanced Nuitka features may not be supported
    """)

# Footer
st.markdown("---")
st.caption("Created by Claude 3.7 Sonnet | Nuitka is a Python compiler that converts your Python code to native executables")
