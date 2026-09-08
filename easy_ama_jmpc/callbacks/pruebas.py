import numpy as np
import scipy.io as sio
import matplotlib.pyplot as plt
from scipy.signal import welch
from scipy.signal.windows import hann

# Cargar el archivo .mat
file_path = 'C:\\Users\\0M00732\\PycharmProjects\\sener\\easy_ama_jmpc\\assets\\ambient_20190430_160000.mat'
data = sio.loadmat(file_path)

# Extraer datos y frecuencias de muestreo
predat_a = data['predat_a']
time_data = (predat_a[0,0][0] - predat_a[0,0][0][0]) * 24 * 60 * 60  # Vector de tiempo en segundos
acceleration_data = predat_a[0,0][3]  # Datos de aceleración
fs = float(predat_a[0,0][2][0,0])     # Frecuencia de muestreo en Hz
labels = predat_a[0,0][1]             # Etiquetas de los sensores

print(f"Datos de aceleración: {acceleration_data.shape}")
print(f"Frecuencia de muestreo: {fs} Hz")

# Configurar gráficos
sf_case = 2  # 1 para figuras separadas, 2 para subplots en una sola figura
num_sensors = 6
fig, axes = plt.subplots(num_sensors, 2, figsize=(15, num_sensors * 3)) if sf_case == 2 else (None, None)

for i in range(num_sensors):
    sensor_data = acceleration_data[:, i]

    print(f"Len sensor {i}: {len(sensor_data)}")
    label = labels[i][0][0]

    if np.any(np.isnan(sensor_data)):
        continue
    
    # Datos en el tiempo
    if sf_case == 1:
        fig, ax1 = plt.subplots(figsize=(8, 4))
    else:
        ax1 = axes[i, 0]
    
    ax1.plot(time_data, sensor_data, color='blue')
    ax1.set_xlabel("Tiempo (s)")
    ax1.set_ylabel("Aceleración (m/s²)")
    ax1.set_title(f"Historial de Aceleración - {label}")
    ax1.grid(True)

    # Calcular la PSD
    window = hann(2**14)  # Ventana Hanning
    noverlap = int(0.66 * len(window))  # 66% de superposición
    f, psd = welch(sensor_data, fs=fs, window=window, noverlap=noverlap, nfft=len(window), scaling='density')

    # Gráfico de PSD
    if sf_case == 1:
        fig, ax2 = plt.subplots(figsize=(8, 4))
    else:
        ax2 = axes[i, 1]

    ax2.semilogy(f, psd, color='blue')
    ax2.set_xlabel("Frecuencia (Hz)")
    ax2.set_ylabel("PSD ((m/s²)²/Hz)")
    ax2.set_title(f"Densidad Espectral de Potencia - {label}")
    ax2.grid(True)

plt.tight_layout()
plt.show()

