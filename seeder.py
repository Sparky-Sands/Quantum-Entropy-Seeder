import time
import sys
from qiskit import QuantumCircuit, transpile, QuantumRegister, ClassicalRegister
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime import SamplerV2 as Sampler
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# ==========================================
# ⚡ SCOUTER CONFIGURATION ⚡
# ==========================================
USE_IBM_HARDWARE = True 
IBM_TOKEN = "INSERT_YOUR_IBM_API_TOKEN_HERE"
# ==========================================

FIFO_PATH = '/tmp/quantum_entropy.fifo'
num_qubits = 8

# 1. Build the base circuit (Explicitly naming registers for SamplerV2)
qr = QuantumRegister(num_qubits, name='q')
cr = ClassicalRegister(num_qubits, name='c')
qc = QuantumCircuit(qr, cr)

for i in range(num_qubits):
    qc.h(qr[i])
qc.measure(qr, cr)

# 2. Configure the chosen backend
if USE_IBM_HARDWARE:
    rprint("[bold yellow]Authenticating with IBM Quantum API...[/bold yellow]")
    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=IBM_TOKEN)
    backend = service.least_busy(operational=True, simulator=False)
    rprint(f"[bold green]Target Locked: Physical QPU ({backend.name})[/bold green]")
    
    qc_compiled = transpile(qc, backend)
    shots_per_batch = 10000
    hardware_type = "Physical IBM QPU"
    sleep_time = 5
    
    # Initialize the new SamplerV2 Primitive
    sampler = Sampler(mode=backend) 
else:
    backend = AerSimulator()
    qc_compiled = qc
    shots_per_batch = 1024
    hardware_type = "Local CPU (AerSimulator)"
    sleep_time = 0.1

def generate_dashboard(bytes_injected, current_status):
    table = Table(show_header=False, expand=True, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold green")
    
    table.add_row("Active Backend", f"{hardware_type}")
    if USE_IBM_HARDWARE:
        table.add_row("Chip Designation", backend.name)
    table.add_row("Qubits Active", str(num_qubits))
    table.add_row("Total Entropy Injected", f"{bytes_injected:,} Bytes")
    
    power_level = (bytes_injected // 1000)
    table.add_row("Current Power Level", f"Over {power_level}k!")
    table.add_row("Pipeline Status", f"[bold yellow]{current_status}[/bold yellow]")
    
    return Panel(
        table, 
        title="[bold yellow]⚡ Quantum Entropy Scouter ⚡[/bold yellow]", 
        border_style="blue",
        padding=(1, 2)
    )

print(f"\nWaiting for rngd to connect to {FIFO_PATH}...")

# 3. Open the pipeline and start streaming
with open(FIFO_PATH, 'wb') as fifo:
    total_bytes = 0
    status = "Active & Streaming" if not USE_IBM_HARDWARE else "Awaiting QPU Queue..."
    
    with Live(generate_dashboard(total_bytes, status), refresh_per_second=4) as live:
        try:
            while True:
                if USE_IBM_HARDWARE:
                    # IBM V2 Primitive Execution
                    job = sampler.run([qc_compiled], shots=shots_per_batch)
                    
                    # Extract bitstrings from the new V2 data structure using the 'c' register
                    memory = job.result()[0].data.c.get_bitstrings()
                else:
                    # Local Simulator Execution
                    job = backend.run(qc_compiled, shots=shots_per_batch, memory=True)
                    memory = job.result().get_memory()
                
                random_bytes = bytearray([int(bitstring, 2) for bitstring in memory])
                
                fifo.write(random_bytes)
                fifo.flush()
                
                total_bytes += len(random_bytes)
                live.update(generate_dashboard(total_bytes, "Data Transmitted! Looping..."))
                
                time.sleep(sleep_time)
                live.update(generate_dashboard(total_bytes, status))

        except BrokenPipeError:
            pass
        except KeyboardInterrupt:
            pass

rprint("\n[bold red][!] Connection severed. Scouter shut down.[/bold red]")
