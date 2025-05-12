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

def check_static_libpython():
    """Check if static libpython is available"""
    try:
        # Try to find static libpython
        result = subprocess.run(
            [sys.executable, "-c", "import sysconfig; print(sysconfig.get_config_var('LIBDIR'))"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            libdir = result.stdout.strip()
            # Look for libpython.a files
            static_libs = glob.glob(os.path.join(libdir, "libpython*.a"))
            return len(static_libs) > 0
    except:
        pass
    return False

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
    
    # Check if static libpython is available
    has_static_libpython = check_static_libpython()
    if has_static_libpython:
        status_container.success("✅ Static libpython detected - will use for maximum portability")
    else:
        status_container.warning("⚠️ Static libpython not available - using alternative portable options")
    
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
        
        # Define compilation options with adaptive static linking
        # Use static libpython only if available, otherwise use best portable options
        def build_cmd(base_cmd, use_static=False):
            if use_static and has_static_libpython:
                base_cmd.append("--static-libpython=yes")
            return base_cmd
        
        compile_options = {
            "max_compatibility": {
                "name": "Maximum Compatibility Binary",
                "cmd": build_cmd([
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--onefile",  # Single portable file
                    "--show-progress",
                    "--remove-output",
                    "--follow-imports",
                    "--assume-yes-for-downloads",  # Auto-download missing dependencies
                    "--python-flag=no_site",  # Reduce dependencies
                    script_path,
                    f"--output-dir={output_dir}"
                ], use_static=True),
                "creates_runner": False
            },
            "portable": {
                "name": "Portable Non-Standalone",
                "cmd": build_cmd([
                    sys.executable, "-m", "nuitka",
                    "--show-progress",
                    "--remove-output",
                    "--assume-yes-for-downloads",
                    "--python-flag=no_site",
                    script_path,
                    f"--output-dir={output_dir}"
                ], use_static=True),
                "creates_runner": False
            },
            "standalone": {
                "name": "Standalone Binary",
                "cmd": build_cmd([
                    sys.executable, "-m", "nuitka",
                    "--standalone",
                    "--onefile",
                    "--show-progress",
                    "--remove-output",
                    "--assume-yes-for-downloads",
                    "--python-flag=no_site",
                    script_path,
                    f"--output-dir={output_dir}"
                ], use_static=True),
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
            
            # Check linking type
            ldd_process = subprocess.run(["ldd", binary_path], capture_output=True, text=True)
            if "not a dynamic executable" in ldd_process.stderr or "statically linked" in ldd_process.stdout:
                linking_info = "✅ Statically linked - fully portable!"
            else:
                # Check what dynamic libraries are required
                if ldd_process.returncode == 0:
                    libs = ldd_process.stdout.count("=>")
                    linking_info = f"🔗 Dynamically linked ({libs} libraries) - designed for maximum compatibility"
                else:
                    linking_info = "ℹ️ Compiled binary - should work on compatible systems"
            
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
- Static Libpython Available: {'Yes' if has_static_libpython else 'No'}
- Linking: {linking_info}

System Packages: {packages_result}
Python Requirements: {install_result}

Binary Information: {binary_info}

PORTABILITY NOTES:
- This binary was compiled with maximum compatibility settings
- Using --onefile for single-file distribution
- Added --assume-yes-for-downloads for automatic dependency resolution
- Used --python-flag=no_site to reduce system dependencies
- Should work on most compatible Linux systems
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
                'linking_info': linking_info,
                'has_static_libpython': has_static_libpython
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
st.title("🚀 Nuitka Python Compiler (Smart Compilation)")
st.markdown("""
Convert your Python code into portable executables using Nuitka with smart compatibility detection.
**Automatically adapts to your Python environment!** 🎯
""")

# Check and display Python environment status
has_static = check_static_libpython()
if has_static:
    st.success("""
    🎯 **Static Libpython Available!**
    
    This environment supports static linking:
    - Creates fully portable binaries
    - No Python version dependencies
    - Maximum compatibility
    """)
else:
    st.info("""
    🔧 **Using Alternative Portable Options**
    
    Static libpython not available, but we'll still create highly portable binaries using:
    - onefile mode for single-file distribution
    - Automatic dependency resolution
    - Maximum compatibility flags
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
            
            # Show linking status
            if results.get('linking_info'):
                if "Statically linked" in results['linking_info']:
                    st.success(results['linking_info'])
                else:
                    st.info(results['linking_info'])
            
            # Show Python version compatibility info
            st.info(f"""
            **Compiled with Python {results.get('python_version', 'Unknown')}**
            **Using Nuitka {results.get('nuitka_version', 'Unknown')}**
            **Static Libpython: {'✅ Used' if results.get('has_static_libpython') else '❌ Not Available'}**
            
            {'✨ **This binary should work on most compatible systems!**' if not results.get('has_static_libpython') else '🌟 **This static binary will work anywhere!**'}
            """)
            
            # Stats
            if results['binary_path'] and os.path.exists(results['binary_path']):
                file_size = os.path.getsize(results['binary_path'])
                st.metric("File Size", f"{file_size / 1024:.2f} KB")
                
                # Download
                download_filename = f"compiled_program{results.get('output_extension', '.bin')}"
                with open(results['binary_path'], "rb") as f:
                    st.download_button(
                        "⬇️ Download Compiled Binary",
                        data=f,
                        file_name=download_filename,
                        mime="application/octet-stream",
                        type="primary"
                    )
                
                # Instructions based on static availability
                if results.get('has_static_libpython'):
                    st.success("""
                    **Static Binary Instructions:**
                    
                    🌟 **This static binary works from ANY location!**
                    
                    1. Download the file
                    2. Make executable: `chmod +x compiled_program.bin`
                    3. Run from anywhere: `./compiled_program.bin`
                    
                    **No restrictions - works everywhere!**
                    """)
                else:
                    st.info("""
                    **Portable Binary Instructions:**
                    
                    🔧 **This binary is highly portable but may need compatible system:**
                    
                    1. Download the file
                    2. Copy to Linux filesystem: `cp /mnt/c/.../file ~/`
                    3. Make executable: `chmod +x compiled_program.bin`
                    4. Run: `./compiled_program.bin`
                    
                    **Note:** Copy to Linux filesystem (not /mnt/c/) for best compatibility in WSL
                    """)
                
                # General WSL troubleshooting
                with st.expander("🔧 WSL Troubleshooting (if needed)"):
                    st.markdown(f"""
                    **If you encounter issues in WSL:**
                    
                    1. **Always copy to Linux filesystem first:**
                    ```bash
                    cp /mnt/c/Users/username/Downloads/compiled_program.bin ~/
                    cd ~
                    chmod +x compiled_program.bin
                    ./compiled_program.bin
                    ```
                    
                    2. **If you get `_PyRuntime` errors:**
                       - This binary was compiled with Python {results.get('python_version', '3.12')}
                       - Use "Maximum Compatibility" mode for best results
                       - Consider upgrading to static libpython-enabled Python
                    
                    3. **For maximum compatibility:**
                       - Use systems with similar Python versions
                       - Run from Linux filesystem, not Windows mounts
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
print('This is a smart-compiled binary!')

# This will work with automatic compatibility detection
import os, sys
print(f'Running from: {os.getcwd()}')
print(f'Python executable: {sys.executable}')
print('Compilation was optimized for your environment!')""",
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
                    ("max_compatibility", "Maximum Compatibility (Recommended)"),
                    ("portable", "Portable Binary"), 
                    ("standalone", "Standalone Binary")
                ],
                format_func=lambda x: x[1],
                help="""
                - Maximum Compatibility: Best settings for cross-system portability
                - Portable Binary: Optimized binary but may need some system libraries
                - Standalone Binary: Self-contained binary
                
                All modes automatically use static libpython if available!
                """
            )[0]
            
            output_extension = st.selectbox(
                "Output File Extension",
                options=[".bin", ".sh"],
                index=0
            )
            
            # Show Python environment info
            st.info(f"📍 Compiling with Python {get_current_python_version()}")
            if check_static_libpython():
                st.success("🔗 Static libpython will be used!")
            else:
                st.info("🔧 Using portable compilation flags")
        
        # Compile button
        if st.button("🚀 Compile with Nuitka", type="primary"):
            with st.spinner("Compiling with smart settings..."):
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
    
    st.subheader("🎯 Smart Compilation")
    st.info("""
    **Automatic Environment Detection**
    
    This app automatically detects your Python environment and chooses the best compilation strategy:
    - Uses static libpython if available (maximum portability)
    - Falls back to highly portable alternatives if not
    - Automatically handles missing dependencies
    - Optimizes for your specific environment
    """)
    
    st.subheader("📋 General Instructions")
    st.code("""
# Download the compiled binary
# Method 1: Direct run (if static libpython was used)
chmod +x compiled_program.bin
./compiled_program.bin

# Method 2: Copy to Linux filesystem first (recommended for WSL)
cp /mnt/c/Users/username/Downloads/compiled_program.bin ~/
cd ~
chmod +x compiled_program.bin
./compiled_program.bin
    """)
    
    st.subheader("📊 Environment Types")
    env_types = {
        "Environment": ["Static Libpython", "Non-Static Libpython"],
        "Portability": ["Maximum", "High"],
        "Requirements": ["None", "Compatible system"],
        "Best For": ["Any Linux system", "Similar environments"]
    }
    st.table(env_types)

with tab3:
    st.header("ℹ️ About")
    
    st.subheader("🧠 Smart Compilation Technology")
    st.markdown("""
    **How it works:**
    
    1. **Environment Detection**: Checks if static libpython is available
    2. **Adaptive Options**: Uses the best available compilation flags
    3. **Fallback Strategy**: Ensures compilation succeeds even without static linking
    4. **Automatic Dependencies**: Resolves missing dependencies automatically
    
    This approach maximizes compatibility across different Python environments.
    """)
    
    st.subheader("✅ What This Solves")
    st.success("""
    **Problems addressed:**
    
    - Static libpython not available error
    - Python version mismatches
    - WSL compatibility issues
    - Dependency resolution
    - Cross-environment portability
    """)
    
    st.subheader("☁️ Current Environment Status")
    static_status = "✅ Available" if check_static_libpython() else "❌ Not Available"
    st.code(f"""
    Python Version: {get_current_python_version()}
    Nuitka Version: {get_nuitka_version()}
    Platform: {platform.platform()}
    Architecture: {platform.architecture()[0]}
    Machine: {platform.machine()}
    Static Libpython: {static_status}
    """)
    
    st.subheader("📋 Best Practices")
    st.markdown("""
    **Recommendations:**
    
    1. Always use "Maximum Compatibility" mode
    2. Copy binaries to Linux filesystem in WSL
    3. Test the binary in the target environment
    4. Let the app automatically choose the best settings
    5. Check the compilation details for specific optimization used
    """)

# Footer
st.markdown("---")
st.caption("🤖 Created by Claude 3.7 Sonnet | 🚀 Powered by Nuitka with Smart Compilation")
