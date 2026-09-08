from dash import Input, Output, State, html
import base64
import pandas as pd
import io
import re
import plotly.graph_objs as go  # Importamos plotly para generar las gráficas
import numpy as np  # Para la FFT y PSD
from scipy.fftpack import fft  # FFT
from scipy.signal import welch, butter, filtfilt, firwin  # PSD y Filtros
import numpy as np
import pandas as pd
from scipy.integrate import cumulative_trapezoid as cumtrapz
from scipy.interpolate import UnivariateSpline
from scipy.stats import linregress
import os
import zipfile
import datetime


# Función para parsear el contenido de un archivo de acelerómetro y extraer campos específicos
def parse_txt_file(content):
    lines = content.split('\n')
    data_lines = []
    is_data_section = False
    current_section = None
    header_dict = {"Recorder": {}, "Sensor": {}, "File": {}, "Acquisition": {}, "Trigger": {}}

    for line in lines:
        if line.strip() == '' or line.startswith("# [ASCII]") or "Filter" in line:
            continue
        if line.startswith("# [Columns]"):
            is_data_section = True
            continue
        if not is_data_section:
            if line.startswith("# ["):
                current_section = re.findall(r"\[(.*?)\]", line)[0]
                if current_section not in ["Recorder", "Sensor", "File", "Acquisition", "Trigger"]:
                    current_section = None
            elif current_section:
                key_value_match = re.match(r"#?\s*(\w+[-\w\s]*?)\s*[=:]\s*(.*)", line)
                if key_value_match:
                    key, value = key_value_match.groups()
                    header_dict[current_section][key.strip()] = value.strip()
        else:
            if not line.startswith("#"):
                data_lines.append(line)

    cleaned_data_lines = [line for line in data_lines if len(line.split()) == 4]

    recorder_name = header_dict.get("Recorder", {}).get('Name', 'Desconocido')
    sensor_name = header_dict.get("Sensor", {}).get('Name', 'Desconocido')
    device_name = f"{recorder_name} - {sensor_name}"
    sampling_frequency = float(header_dict.get("Acquisition", {}).get('Rate', 0.0))
    num_samples = int(header_dict.get("File", {}).get('Samples', 0))
    units = header_dict.get("Sensor", {}).get('Unit', 'Desconocido')
    peak_x = float(header_dict.get("File", {}).get('Peak-X', 0.0))
    peak_y = float(header_dict.get("File", {}).get('Peak-Y', 0.0))
    peak_z = float(header_dict.get("File", {}).get('Peak-Z', 0.0))
    pre_event = float(header_dict.get("Trigger", {}).get('PreEvent', 0.0))
    post_event = float(header_dict.get("Trigger", {}).get('PostEvent', 0.0))

    if cleaned_data_lines:
        data = pd.read_csv(io.StringIO("\n".join(cleaned_data_lines)), sep='\s+', header=None)
        if data.shape[1] == 4:
            data.columns = ['time', 'X', 'Y', 'Z']
        else:
            raise ValueError("El archivo no tiene el formato esperado.")
    else:
        raise ValueError("No se encontraron datos en el archivo.")

    return {
        "header": {
            "device_name": device_name,
            "sampling_frequency": sampling_frequency,
            "num_samples": num_samples,
            "units": units,
            "peak_x": peak_x,
            "peak_y": peak_y,
            "peak_z": peak_z,
            "pre_event": pre_event,
            "post_event": post_event
        },
        "data": data
    }

# Función para construir gráficas de desplazamiento.

def get_graficas_desplazamiento(desp_x, desp_y, desp_z, tiempo, titulo="Desplazamiento"):
    displacement_filtered_fig = go.Figure()
    displacement_filtered_fig.add_trace(go.Scattergl(
        x=tiempo, 
        y=desp_x, 
        mode='lines', 
        name='X'
    ))
    displacement_filtered_fig.add_trace(go.Scattergl(
        x=tiempo, 
        y=desp_y, 
        mode='lines', 
        name='Y'
    ))
    displacement_filtered_fig.add_trace(go.Scattergl(
        x=tiempo, 
        y=desp_z, 
        mode='lines', 
        name='Z'
    ))
    displacement_filtered_fig.update_layout(
        title=titulo, 
        xaxis_title="Tiempo (s)", 
        yaxis_title="Desplazamiento (m)"
    )
    return displacement_filtered_fig

def get_graficas_desplazamiento_z(desp_z, tiempo, titulo="Desplazamiento"):
    displacement_filtered_fig = go.Figure()

    displacement_filtered_fig.add_trace(go.Scattergl(
        x=tiempo, 
        y=desp_z, 
        mode='lines', 
        name='Z',
        showlegend=True
    ))
    displacement_filtered_fig.update_layout(
        title=titulo, 
        xaxis_title="Tiempo (s)", 
        yaxis_title="Desplazamiento (m)"
    )
    return displacement_filtered_fig

# Función para construir gráficas de velocidad.
def calculate_velocity(acceleration, time):
    """
    Calcula la velocidad a partir de datos de aceleración mediante integración.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración.
    - time: array numpy con los datos de tiempo.

    Retorna:
    - velocity: array numpy con los datos de velocidad.
    """
    # Integración de la aceleración para obtener la velocidad
    velocity = cumtrapz(acceleration, time, initial=0)

    return velocity

def calculate_velocity_deriva_acel(acceleration, time):
    """
    Calcula la velocidad a partir de datos de aceleración mediante integración y aplicando corrección de deriva a la aceleración.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración.
    - time: array numpy con los datos de tiempo.

    Retorna:
    - velocity: array numpy con los datos de velocidad.
    """
    # Corrección de deriva en la aceleración
    # acceleration_corrected = acceleration - np.mean(acceleration)
    acceleration_corrected = acceleration - np.mean(acceleration[:2000])

    # Integración de la aceleración para obtener la velocidad
    velocity = cumtrapz(acceleration_corrected, time, initial=0)

    return velocity

def clean_signal_using_psd_peaks(acceleration, fs, f_low, f_high, n_peaks, percentage):
    from scipy.signal import welch, find_peaks
    """
    Limpia la señal de aceleración seleccionando los picos más energéticos en la PSD.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración.
    - fs: Frecuencia de muestreo en Hz.
    - f_low: Frecuencia de corte baja en Hz.
    - f_high: Frecuencia de corte alta en Hz.
    - n_peaks: Número de picos a conservar.
    - percentage: Valor porcentual (entre 0 y 1) para filtrar picos según su altura.

    Retorna:
    - cleaned_signal: La señal reconstruida utilizando únicamente las frecuencias seleccionadas.
    """
    # Número de muestras
    N = len(acceleration)
    
    # Calcular la FFT
    fft_acceleration = np.fft.fft(acceleration)
    # Obtener las frecuencias correspondientes
    freqs = np.fft.fftfreq(N, d=1/fs)

    # Calcular la PSD
    psd = (1/N) * np.abs(fft_acceleration)**2

    # Crear máscara de frecuencias dentro del rango deseado
    freq_mask = (np.abs(freqs) >= f_low) & (np.abs(freqs) <= f_high)

    # Aplicar la máscara de frecuencia a la FFT y a la PSD
    fft_filtered = np.zeros_like(fft_acceleration, dtype=complex)
    fft_filtered[freq_mask] = fft_acceleration[freq_mask]
    psd_filtered = np.zeros_like(psd)
    psd_filtered[freq_mask] = psd[freq_mask]

    # Considerar solo frecuencias positivas para la detección de picos
    positive_freqs = freqs[freqs >= 0]
    positive_psd = psd_filtered[freqs >= 0]

    # Encontrar picos en la PSD
    peak_indices, properties = find_peaks(positive_psd)
    peak_heights = positive_psd[peak_indices]

    # Verificar si se encontraron picos
    if len(peak_heights) == 0:
        raise ValueError("No se encontraron picos en el rango de frecuencias especificado.")

    # Encontrar la altura máxima de los picos
    max_peak_height = np.max(peak_heights)

    # Aplicar el umbral porcentual para filtrar picos
    threshold = percentage * max_peak_height
    significant_peaks = peak_indices[peak_heights >= threshold]

    # Si hay más picos que los deseados, seleccionar los n_peaks más altos
    if len(significant_peaks) > n_peaks:
        # Ordenar los picos por altura descendente
        sorted_indices = np.argsort(peak_heights[peak_heights >= threshold])[::-1]
        significant_peaks = significant_peaks[sorted_indices][:n_peaks]
    else:
        # Ordenar todos los picos por altura descendente
        sorted_indices = np.argsort(peak_heights)[::-1]
        significant_peaks = significant_peaks[sorted_indices][:n_peaks]

    # Crear una máscara para las frecuencias significativas
    significant_freqs_mask = np.zeros_like(fft_acceleration, dtype=bool)

    # Mapear los índices de frecuencias positivas a los índices de FFT
    for idx in significant_peaks:
        freq = positive_freqs[idx]
        # Encontrar el índice en el arreglo FFT (frecuencias positivas y negativas)
        fft_idx = np.argmin(np.abs(freqs - freq))
        significant_freqs_mask[fft_idx] = True
        # Incluir la frecuencia negativa correspondiente
        fft_idx_neg = np.argmin(np.abs(freqs + freq))
        significant_freqs_mask[fft_idx_neg] = True

    # Reconstruir la señal utilizando solo las frecuencias significativas
    fft_cleaned = np.zeros_like(fft_acceleration, dtype=complex)
    fft_cleaned[significant_freqs_mask] = fft_acceleration[significant_freqs_mask]

    # Transformada inversa para obtener la señal limpia
    cleaned_signal = np.fft.ifft(fft_cleaned)

    # Tomar la parte real de la señal limpia
    cleaned_signal = np.real(cleaned_signal)

    return cleaned_signal

# Función para superposición de frecuencias
def calculate_displacement_superposition_psd(acceleration, time, num_modes=20, default_damping=0.002):
    """
    Calcula el desplazamiento a través de la superposición de frecuencias dominantes,
    identificadas automáticamente a partir de los picos en la PSD.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración (en m/s²)
    - time: array numpy con los datos de tiempo (en segundos)
    - num_modes: número de modos dominantes a considerar (por defecto 3)
    - default_damping: factor de amortiguamiento por defecto para cada modo (valor típico entre 0 y 1)

    Retorna:
    - displacement_time: array numpy con el desplazamiento calculado (en metros)
    """
    import numpy as np
    from scipy.signal import welch, find_peaks

    print(acceleration)
    print("Tipo de aceleración: ", type(acceleration))
    print("forma de aceleración: ", acceleration.shape)

    # Parámetros iniciales
    fs = 1 / (time[1] - time[0])  # Frecuencia de muestreo
    N = len(acceleration)
    freqs = np.fft.rfftfreq(N, d=1/fs)
    omega = 2 * np.pi * freqs

    # Cálculo de la PSD utilizando el método de Welch
    f_psd, Pxx = welch(acceleration, fs=fs, nperseg=512)

    # Identificación de picos en la PSD
    peaks, _ = find_peaks(Pxx, height=np.max(Pxx)*0.001)  # Ajustar el umbral según sea necesario
    peak_freqs = f_psd[peaks]

    # Ordenar los picos por amplitud decreciente
    peak_heights = Pxx[peaks]
    sorted_indices = np.argsort(peak_heights)[::-1]
    dominant_frequencies = peak_freqs[sorted_indices][:num_modes]

    # Asignar el factor de amortiguamiento por defecto a todos los modos
    damping_ratios = [default_damping] * len(dominant_frequencies)

    # FFT de la aceleración
    fft_acceleration = np.fft.rfft(acceleration)

    # Inicializar desplazamiento total en frecuencia
    U_total = np.zeros_like(fft_acceleration, dtype=complex)

    for i, f_n in enumerate(dominant_frequencies):
        omega_n = 2 * np.pi * f_n
        zeta_n = damping_ratios[i]
        m_n = 1  # Supongamos masa modal unitaria para simplificar
        c_n = 2 * m_n * omega_n * zeta_n
        k_n = m_n * omega_n**2

        # Función de transferencia modal
        denom = -m_n * omega**2 + 1j * c_n * omega + k_n

        # Evitar divisiones por cero añadiendo un pequeño valor epsilon al denominador cuando sea necesario
        epsilon = 1e-6
        denom = np.where(np.abs(denom) < epsilon, denom + epsilon, denom)

        H_n = 1 / denom

        # Respuesta modal
        U_n = H_n * fft_acceleration

        # Superposición de respuestas modales
        U_total += U_n

    # Transformada inversa para obtener el desplazamiento en el tiempo
    displacement_time = np.fft.irfft(U_total, n=N)

    return displacement_time

def filtro_pasa_banda_frecuencia(acceleration, time, f_low, f_high):
    """
    Filtra una señal de aceleración en el dominio de la frecuencia.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración (en m/s²)
    - time: array numpy con los datos de tiempo (en segundos)
    - f_low: Frecuencia de corte baja en Hz.
    - f_high: Frecuencia de corte alta en Hz.

    Retorna:
    - acceleration_filtered: array numpy con los datos de aceleración filtrados.
    """
    # Parámetros iniciales
    fs = 1 / (time[1] - time[0])  # Frecuencia de muestreo
    N = len(acceleration)
    freqs = np.fft.rfftfreq(N, d=1/fs)

    # FFT de la aceleración
    fft_acceleration = np.fft.rfft(acceleration)

    # Crear una máscara para las frecuencias dentro del rango deseado
    freq_mask = (freqs >= f_low) & (freqs <= f_high)

    # Aplicar la máscara de frecuencia a la FFT
    fft_filtered = np.zeros_like(fft_acceleration, dtype=complex)
    fft_filtered[freq_mask] = fft_acceleration[freq_mask]

    # Transformada inversa para obtener la señal filtrada en el tiempo
    acceleration_filtered = np.fft.irfft(fft_filtered, n=N)

    return acceleration_filtered

# Función para aplicar filtro FIR
def apply_fir_filter(filter_type, freq_cutoff1, freq_cutoff2, data, fs):
    nyquist = 0.5 * fs
    numtaps = 2001  # Número de coeficientes del filtro (ajustar según necesidad)
    
    if filter_type == 'lowpass':
        cutoff = freq_cutoff1 / nyquist
        b = firwin(numtaps, cutoff, window='hamming', pass_zero='lowpass')
    elif filter_type == 'highpass':
        cutoff = freq_cutoff1 / nyquist
        b = firwin(numtaps, cutoff, window='hamming', pass_zero='highpass')
    elif filter_type == 'bandpass':
        cutoff = [freq_cutoff1 / nyquist, freq_cutoff2 / nyquist]
        b = firwin(numtaps, cutoff, window='hamming', pass_zero=False)
    elif filter_type == 'bandstop':
        cutoff = [freq_cutoff1 / nyquist, freq_cutoff2 / nyquist]
        b = firwin(numtaps, cutoff, window='hamming', pass_zero='bandstop')
    else:
        raise ValueError("Tipo de filtro no reconocido. Debe ser 'lowpass', 'highpass', 'bandpass' o 'bandstop'.")

    filtered_data = {}
    for axis in ['X', 'Y', 'Z']:
        filtered_data[axis] = filtfilt(b, 1.0, data[axis])

    return filtered_data

# Función para aplicar un filtro
def apply_filter(filter_type, freq_cutoff1, freq_cutoff2, data, fs):
    if filter_type == 'lowpass':
        b, a = butter(6, freq_cutoff1 / (0.5 * fs), btype='low')
    elif filter_type == 'highpass':
        b, a = butter(6, freq_cutoff1 / (0.5 * fs), btype='high')
    elif filter_type == 'bandpass':
        b, a = butter(6, [freq_cutoff1 / (0.5 * fs), freq_cutoff2 / (0.5 * fs)], btype='band')
    elif filter_type == 'bandstop':
        b, a = butter(4, [freq_cutoff1 / (0.5 * fs), freq_cutoff2 / (0.5 * fs)], btype='bandstop')

    filtered_data = {}
    for axis in ['X', 'Y', 'Z']:
        filtered_data[axis] = filtfilt(b, a, data[axis])

    return filtered_data

def butter_pasa_altas(acceleration, time, cutoff, fs, order=3):
    """
    Filtra una señal de aceleración en el dominio del tiempo utilizando un filtro Butterworth pasa altas.

    Parámetros:
    - acceleration: array numpy con los datos de aceleración (en m/s²)
    - time: array numpy con los datos de tiempo (en segundos)
    - cutoff: Frecuencia de corte en Hz.
    - fs: Frecuencia de muestreo en Hz.
    - order: Orden del filtro (por defecto 3)

    Retorna:
    - acceleration_filtered: array numpy con los datos de aceleración filtrados.
    """
    # Crear el filtro Butterworth pasa altas
    b, a = butter(order, cutoff / (0.5 * fs), btype='high')

    # Aplicar el filtro a la señal de aceleración
    acceleration_filtered = filtfilt(b, a, acceleration)

    return acceleration_filtered

def generate_report_and_files(acceleration, time, acell_corregida, velocity, vel_corregida, displacement, beta, alfa, beta_vel, alfa_vel):
    # Obtener la fecha y hora actuales para nombrar el archivo ZIP
    fecha_hora = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"calculos_{fecha_hora}.zip"

    # Crear una carpeta temporal para almacenar los archivos
    temp_folder = f"temp_{fecha_hora}"
    os.makedirs(temp_folder, exist_ok=True)

    # Guardar los vectores en archivos CSV
    data = {
        'time': time,
        'acceleration': acceleration,
        'acceleration_corrected': acell_corregida,
        'velocity': velocity,
        'velocity_corrected': vel_corregida,
        'displacement': displacement
    }
    df = pd.DataFrame(data)
    csv_filename = os.path.join(temp_folder, 'resultados.csv')
    df.to_csv(csv_filename, index=False)

    # Crear el informe TXT
    report_content = f"""Informe de Cálculo de Desplazamiento
Fecha y Hora: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Parámetros de Corrección de Aceleración:
- Beta (promedio inicial): {beta}
- Alfa (promedio final): {alfa}

Parámetros de Corrección de Velocidad:
- Beta_vel (promedio inicial de velocidad): {beta_vel}
- Alfa_vel (promedio final de velocidad): {alfa_vel}

Los vectores de datos y resultados intermedios se encuentran en el archivo CSV adjunto: resultados.csv

"""

    report_filename = os.path.join(temp_folder, 'informe.txt')
    with open(report_filename, 'w') as report_file:
        report_file.write(report_content)

    # Crear el archivo ZIP con todos los archivos generados
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        zipf.write(csv_filename, arcname='resultados.csv')
        zipf.write(report_filename, arcname='informe.txt')

    # Eliminar la carpeta temporal y los archivos
    os.remove(csv_filename)
    os.remove(report_filename)
    os.rmdir(temp_folder)

    print(f"Los archivos de resultados han sido guardados en el archivo ZIP: {zip_filename}")

# Función para calcular el desplazamiento a partir de datos de aceleración mediante doble integración y aplicando corrección de deriva unicamente sobre serie de aceleración; utilizando todos los datos para calcular el promedio con el fin de corregir la deriva.
def calculate_displacement_simple(acceleration, time):
    """
    Calcula el desplazamiento a partir de datos de aceleración mediante doble integración,
    sin aplicar filtrado, pero corrigiendo la deriva en la aceleración utilizando el promedio
    de todos los datos.

    Parámetros:
    - acceleration: array numpy o pandas Series con los datos de aceleración (en m/s²)
    - time: array numpy o pandas Series con los datos de tiempo (en segundos)

    Retorna:
    - displacement: array numpy con el desplazamiento calculado (en metros)
    """

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acceleration, time, initial=0)

    # 3. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity, time, initial=0)

    return displacement

def func_1_0(prom_inicial, promedio_final, t_finl, t):
    """
    Función para calcular el valor de la función 1 - t/t_final.
    
    Parámetros:
    - t_finl: valor final de t
    - t: valor actual de t
    
    Retorna:
    - res: valor de la función
    """

    t_1 = prom_inicial/2
    t_2 = t_finl - promedio_final/2

    m = -1/(t_2 - t_1)

    res = 1 + m*(t - t_1)
    
    return res

def func_0_1(prom_inicial, promedio_final, t_finl, t):
    """
    Función para calcular el valor de la función t/t_final.

    Parámetros:
    - t_finl: valor final de t
    - t: valor actual de t

    Retorna:
    - res: valor de la función
    """

    t_1 = prom_inicial/2
    t_2 = t_finl - promedio_final/2

    m = 1/(t_2 - t_1)
    
    res = 1 + m*(t - t_2)

    return res


def calculate_displacement_simple_vel(acceleration, time, init_time, final_time):
    """
    Calcula el desplazamiento a partir de datos de aceleración.
    """

    if init_time == 0:
        init_time = 5

    if final_time == 0:
        final_time = 5

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    # 1. Corrección de deriva en la aceleración
    # init_time = 3
    # final_time = 25

    t = time[1]-time[0]

    beta = np.mean(acceleration[:int(init_time/t)])*0

    alfa = np.mean(acceleration[-int(final_time/t):])*0

    # print(f"Beta: {beta}")
    # print(f"Alfa: {alfa}")

    acell_corregida = []
    for index, t_actual in enumerate(time):
        acell_corregida.append(acceleration[index] - (alfa*func_0_1(init_time, final_time, time[-1], t_actual) + beta*func_1_0(init_time, final_time, time[-1], t_actual)))

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acell_corregida, time, initial=0)

    # 3. Corrección de deriva en la velocidad
    beta_vel = np.mean(velocity[:int(init_time/t)])

    alfa_vel = np.mean(velocity[-int(final_time/t):])

    print(f"Beta_vel: {beta_vel}")
    print(f"Alfa_vel: {alfa_vel}")

    vel_corregida = []
    for index, t_actual in enumerate(time):
        vel_corregida.append(velocity[index] - (alfa_vel*func_0_1(init_time, final_time, time[-1], t_actual) + beta_vel*func_1_0(init_time, final_time, time[-1], t_actual)))

    # 4. Integración de velocidad a desplazamiento
    displacement = cumtrapz(vel_corregida, time, initial=0)

    alfa_desp = np.mean(displacement[-int(final_time/t):])
    beta_desp = np.mean(displacement[:int(init_time/t)])

    desp_corregido = []
    for index, t_actual in enumerate(time):
        desp_corregido.append(displacement[index] - (alfa_desp*func_0_1(init_time, final_time, time[-1], t_actual) + beta_desp*func_1_0(init_time, final_time, time[-1], t_actual)))

    return acell_corregida, velocity, vel_corregida, displacement, desp_corregido

# generate_report_and_files(acceleration, time, acell_corregida, velocity, vel_corregida, displacement, beta, alfa, beta_vel, alfa_vel)




# Desplazamiento José María recargado
def calculate_displacement_simple_vel_slope(acceleration, time):
    """
    Calcula el desplazamiento a partir de datos de aceleración mediante doble integración,
    sin aplicar filtrado, pero corrigiendo la deriva en la aceleración utilizando el promedio
    de todos los datos.

    Parámetros:
    - acceleration: array numpy o pandas Series con los datos de aceleración (en m/s²)
    - time: array numpy o pandas Series con los datos de tiempo (en segundos)

    Retorna:
    - displacement: array numpy con el desplazamiento calculado (en metros)
    """

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acceleration, time, initial=0)

    # 3. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity, time, initial=0)

    # Realizar regresión lineal
    slope, intercept, r_value, p_value, std_err = linregress(time, displacement)

    print(f"Pendiente (slope): {slope}")
    print(f"Intersección (intercept): {intercept}")
    print(f"Coeficiente de correlación (r_value): {r_value}")
    print(f"Valor p (p_value): {p_value}")
    print(f"Error estándar (std_err): {std_err}")


    prom_desplazamiento = np.mean(displacement[-250:])

    # velocity_corrected = velocity - prom_desplazamiento/(time[-1])

    velocity_corrected = velocity - slope

    desp_corrected = cumtrapz(velocity_corrected, time, initial=0)

    # velocity_corrected = velocity - np.mean(velocity[-500:]/(time[-1]))

    return desp_corrected

def calculate_displacement_vel_slope(velocity, time):

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(velocity, pd.Series):
        velocity = velocity.values
    if isinstance(time, pd.Series):
        time = time.values

    # 3. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity, time, initial=0)

    # Realizar regresión lineal
    slope, intercept, r_value, p_value, std_err = linregress(time, displacement)

    print(f"Pendiente (slope): {slope}")
    print(f"Intersección (intercept): {intercept}")
    print(f"Coeficiente de correlación (r_value): {r_value}")
    print(f"Valor p (p_value): {p_value}")
    print(f"Error estándar (std_err): {std_err}")

    velocity_corrected = velocity - slope

    desp_corrected = cumtrapz(velocity_corrected, time, initial=0)

    # velocity_corrected = velocity - np.mean(velocity[-500:]/(time[-1]))

    return desp_corrected

# Función para calcular el desplazamiento a partir de datos de aceleración mediante doble integración y aplicando corrección de deriva unicamente sobre serie de aceleración; utilizando todos los datos para calcular el promedio con el fin de corregir la deriva.
def calculate_displacement_deriva_acel(acceleration, time):
    """
    Calcula el desplazamiento a partir de datos de aceleración mediante doble integración,
    sin aplicar filtrado, pero corrigiendo la deriva en la aceleración utilizando el promedio
    de todos los datos.

    Parámetros:
    - acceleration: array numpy o pandas Series con los datos de aceleración (en m/s²)
    - time: array numpy o pandas Series con los datos de tiempo (en segundos)

    Retorna:
    - displacement: array numpy con el desplazamiento calculado (en metros)
    """

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    # 1. Corrección de deriva en aceleración utilizando el promedio de todos los datos
    acceleration_corrected = acceleration - np.mean(acceleration[:1000])

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acceleration_corrected, time, initial=0)

    # 3. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity, time, initial=0)

    return displacement

# ------------------------------------------------------------------------------------
def calculate_displacement_deriva_acel_deriva_vel(acceleration, time):
    """
    Calcula el desplazamiento a partir de datos de aceleración mediante doble integración,
    sin aplicar filtrado, pero corrigiendo la deriva en la aceleración utilizando el promedio
    de todos los datos.

    Parámetros:
    - acceleration: array numpy o pandas Series con los datos de aceleración (en m/s²)
    - time: array numpy o pandas Series con los datos de tiempo (en segundos)

    Retorna:
    - displacement: array numpy con el desplazamiento calculado (en metros)
    """

    # Si acceleration o time son Series de pandas, convertir a numpy array
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    # 1. Corrección de deriva en aceleración utilizando el promedio de todos los datos
    acceleration_corrected = acceleration - np.mean(acceleration[:1000])

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acceleration_corrected, time, initial=0)

    velocity_corrected = velocity - np.mean(velocity)

    # 3. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity_corrected, time, initial=0)

    return displacement

def calculate_displacement_filtered(acceleration, time):
    """
    Calcula el desplazamiento vertical de una estructura a partir de datos de aceleración,
    corrigiendo la deriva mediante la estimación del sesgo del acelerómetro y aplicando
    métodos avanzados de detrending, preservando las componentes de baja frecuencia
    para capturar la deflexión cuasi-estática.

    Parameters:
    - acceleration: numpy array o pandas Series con la señal de aceleración (en m/s²)
    - time: numpy array o pandas Series con la serie temporal asociada

    Returns:
    - displacement_final: numpy array con el desplazamiento calculado en metros
    """

    # Convertir a arrays de NumPy si son Series de Pandas
    if isinstance(acceleration, pd.Series):
        acceleration = acceleration.values
    if isinstance(time, pd.Series):
        time = time.values

    dt = time[1] - time[0]
    fs = 1 / dt  # Frecuencia de muestreo

    # 1. Estimación y eliminación del sesgo (bias) del acelerómetro
    # Suponiendo que al inicio y al final la aceleración debería ser cero
    n_samples = len(acceleration)
    n_initial = int(n_samples * 0.15)  # 5% inicial
    n_final = int(n_samples * 0.15)    # 5% final

    # Calcular la media de los segmentos inicial y final
    bias_initial = np.mean(acceleration[:n_initial])
    bias_final = np.mean(acceleration[-n_final:])
    bias = (bias_initial + bias_final) / 2

    # Restar el bias de la aceleración
    acceleration_corrected = acceleration - bias

    # 2. Integración de aceleración a velocidad
    velocity = cumtrapz(acceleration_corrected, time, initial=0)

    # 3. Eliminación de deriva en velocidad utilizando splines
    spline_order = 4  # Orden del spline (ajustar según sea necesario)
    spline_smoothing = 1e-2  # Factor de suavizado (ajustar según sea necesario)
    spline_vel = UnivariateSpline(time, velocity, k=spline_order, s=spline_smoothing)
    velocity_detrended = velocity - spline_vel(time)

    # 4. Integración de velocidad a desplazamiento
    displacement = cumtrapz(velocity_detrended, time, initial=0)

    # 5. Eliminación de deriva en desplazamiento utilizando splines
    spline_disp = UnivariateSpline(time, displacement, k=spline_order, s=spline_smoothing)
    displacement_detrended = displacement - spline_disp(time)

    # 6. Aplicar condiciones de contorno (desplazamiento cero al inicio y al final)
    displacement_final = displacement_detrended - np.linspace(displacement_detrended[0],
                                                             displacement_detrended[-1],
                                                             len(displacement_detrended))

    return displacement_final

def register_callbacks(app):
    @app.callback(
        [Output('file-info', 'children'), Output('main-graph', 'figure'),
         Output('additional-graph-1', 'figure'), Output('additional-graph-2', 'figure'),
         Output('graph-16', 'figure'), Output('graph-17', 'figure'),
         Output('graph-4', 'figure'), Output('graph-5', 'figure'),
         Output('graph-6', 'figure'), Output('graph-7', 'figure'),
         Output('graph-8', 'figure'), Output('graph-9', 'figure'),
         Output('graph-18', 'figure'), Output('graph-19', 'figure'),
         Output('graph-12', 'figure'), Output('graph-13', 'figure'),],
        [Input('upload-data', 'contents'), Input('main-graph', 'relayoutData')],
        [State('upload-data', 'filename')]
    )
    def update_output(file_contents, relayout_data, file_name):

        # Verificar si se ha cargado un archivo
        if file_contents is not None:
            print("Archivo cargado correctamente.")
            content_type, content_string = file_contents.split(',')
            decoded = base64.b64decode(content_string).decode('utf-8')
            parsed_data = parse_txt_file(decoded)

            # Información del archivo
            header_info = parsed_data['header']
            header_str = f"""
Archivo cargado: {file_name}
Dispositivo: {header_info['device_name']}
Frecuencia de muestreo: {header_info['sampling_frequency']} Hz
Número de muestras: {header_info['num_samples']}
Unidades: {header_info['units']}
"""

            # Datos originales
            data = parsed_data['data']
            sampling_freq = header_info['sampling_frequency']

            # Verificar si hay una selección en relayout_data
            data_segmented = data
            if relayout_data and 'selections' in relayout_data:
                print(f"Relayout data detectado: {relayout_data}")
                selections = relayout_data['selections']

                # Comprobar si hay al menos una selección válida
                if len(selections) > 0 and 'x0' in selections[0] and 'x1' in selections[0]:
                    start_time = selections[0]['x0']
                    end_time = selections[0]['x1']
                    mask = (data['time'] >= start_time) & (data['time'] <= end_time)
                    data_segmented = data.loc[mask]
                    print(f"Segmento de datos seleccionado: {start_time} - {end_time}")

                    # Mostrar el rango seleccionado en la información del archivo
                    header_str += f"\nRango seleccionado: {start_time:.2f} - {end_time:.2f} segundos"
                else:
                    print("No se detectó un rango válido en la selección.")
            else:
                print("No se detectó relayout_data o no hay selecciones.")

            # Mostrar picos de la señal original
            header_str += f"\nPicos de aceleración: X: {header_info['peak_x']}, Y: {header_info['peak_y']}, Z: {header_info['peak_z']}"
            header_str += f"\nPre-Event Time: {header_info['pre_event']} s"
            header_str += f"\nPost-Event Time: {header_info['post_event']} s"

            # Gráfico de señales originales
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=data['time'], y=data['X'], mode='lines', name='Aceleración X'))
            fig.add_trace(go.Scatter(x=data['time'], y=data['Y'], mode='lines', name='Aceleración Y'))
            fig.add_trace(go.Scatter(x=data['time'], y=data['Z'], mode='lines', name='Aceleración Z'))
            fig.update_layout(
                title="Series de Aceleración",
                xaxis_title="Tiempo (s)",
                yaxis_title="Aceleración",
                dragmode='select'  # Habilita la selección de datos en la gráfica
            )

            # Recalcular FFT y PSD con datos segmentados
            fft_fig = go.Figure()
            psd_fig = go.Figure()
            for axis in ['X', 'Y', 'Z']:
                fft_vals = fft(np.asarray(data_segmented[axis]))
                fft_freqs = np.fft.fftfreq(len(fft_vals), 1.0 / sampling_freq)
                fft_fig.add_trace(go.Scatter(
                    x=fft_freqs[:len(fft_vals)//2], 
                    y=np.abs(fft_vals[:len(fft_vals)//2]), 
                    mode='lines', 
                    name=f'FFT {axis}'
                ))

                freqs, psd_vals = welch(data_segmented[axis], fs=sampling_freq, nperseg=1024)
                psd_fig.add_trace(go.Scatter(
                    x=freqs, 
                    y=psd_vals, 
                    mode='lines', 
                    name=f'PSD {axis}'
                ))

            fft_fig.update_layout(
                title="FFT - Señales Segmentadas", 
                xaxis_title="Frecuencia (Hz)", 
                yaxis_title="Magnitud"
            )
            psd_fig.update_layout(
                title="PSD - Señales Segmentadas. Welch 1024", 
                xaxis_title="Frecuencia (Hz)", 
                yaxis_title="Densidad de Potencia"
            )

            # Velocidad sin correcciones

            vel_data_x = calculate_velocity(data_segmented['X'], data_segmented['time'])
            vel_data_y = calculate_velocity(data_segmented['Y'], data_segmented['time'])
            vel_data_z = calculate_velocity(data_segmented['Z'], data_segmented['time'])

            velocity_fig = get_graficas_desplazamiento(vel_data_x, vel_data_y, vel_data_z, data_segmented['time'], "Velocidad Simple S (X, Y, Z)")

            # Velocidad con correcciones

            vel_data_der_x = calculate_velocity_deriva_acel(data_segmented['X'], data_segmented['time'])
            vel_data_der_y = calculate_velocity_deriva_acel(data_segmented['Y'], data_segmented['time'])
            vel_data_der_z = calculate_velocity_deriva_acel(data_segmented['Z'], data_segmented['time'])

            velocity_deriva_acel_fig = get_graficas_desplazamiento(vel_data_der_x, vel_data_der_y, vel_data_der_z, data_segmented['time'], "Velocidad Deriva Aceleración (X, Y, Z)")

            # Desplazamiento simple de doble integración sin ajustes de ningún tipo

            displacement_data_x = calculate_displacement_simple(data_segmented['X'], data_segmented['time'])
            displacement_data_y = calculate_displacement_simple(data_segmented['Y'], data_segmented['time'])
            displacement_data_z = calculate_displacement_simple(data_segmented['Z'], data_segmented['time'])

            displacement_fig = get_graficas_desplazamiento(displacement_data_x, displacement_data_y, displacement_data_z, data_segmented['time'], "Desplazamiento Simple SS (X, Y, Z)")

            # Desplazamiento con correcciones de deriva en aceleración

            desp_der_acel_x = calculate_displacement_deriva_acel(data_segmented['X'], data_segmented['time'])
            desp_der_acel_y = calculate_displacement_deriva_acel(data_segmented['Y'], data_segmented['time'])
            desp_der_acel_z = calculate_displacement_deriva_acel(data_segmented['Z'], data_segmented['time'])

            displacement_deriva_acel_fig = get_graficas_desplazamiento(desp_der_acel_x, desp_der_acel_y, desp_der_acel_z, data_segmented['time'], "Desplazamiento Deriva Aceleración (X, Y, Z)")

            # Desplazamiento con correcciones de deriva en aceleración y velocidad

            desp_der_acel_vel_x = calculate_displacement_deriva_acel_deriva_vel(data_segmented['X'], data_segmented['time'])
            desp_der_acel_vel_y = calculate_displacement_deriva_acel_deriva_vel(data_segmented['Y'], data_segmented['time'])
            desp_der_acel_vel_z = calculate_displacement_deriva_acel_deriva_vel(data_segmented['Z'], data_segmented['time'])

            displacement_deriva_acel_vel_fig = get_graficas_desplazamiento(desp_der_acel_vel_x, desp_der_acel_vel_y, desp_der_acel_vel_z, data_segmented['time'], "Desplazamiento Deriva Aceleración y Velocidad (X, Y, Z)")

            # Desplazamiento algoritmo JM

            filtered_data_fir = apply_fir_filter('bandpass', 0.05, 100, data_segmented, sampling_freq)

            # filtered_data_frec_x = filtro_pasa_banda_frecuencia(data_segmented['X'], data_segmented['time'], 0.05, 100)
            # filtered_data_frec_y = filtro_pasa_banda_frecuencia(data_segmented['Y'], data_segmented['time'], 0.05, 100)
            # filtered_data_frec_z = filtro_pasa_banda_frecuencia(data_segmented['Z'], data_segmented['time'], 0.05, 100)

            acel_corr_x, vel_x, vel_corr_x, desp_x, desp_fir_der_acel_x = calculate_displacement_simple_vel(filtered_data_fir['X'], data_segmented['time'], header_info['pre_event'], header_info['post_event'])
            acel_corr_y, vel_y, vel_corr_y, desp_y, desp_fir_der_acel_y = calculate_displacement_simple_vel(filtered_data_fir['Y'], data_segmented['time'], header_info['pre_event'], header_info['post_event'])
            acel_corr_z, vel_z, vel_corr_z, desp_z, desp_fir_der_acel_z = calculate_displacement_simple_vel(filtered_data_fir['Z'], data_segmented['time'], header_info['pre_event'], header_info['post_event'])

            acel_corr_fig = get_graficas_desplazamiento(acel_corr_x, acel_corr_y, acel_corr_z, data_segmented['time'], "Aceleración Fir 0.05 - 100 (Z) Deriva corregida")

            vel_fig = get_graficas_desplazamiento(vel_x, vel_y, vel_z, data_segmented['time'], "Velocidad Fir 0.05 - 100 (Z) Integral sobre aceleración corregida")

            vel_corr_fig = get_graficas_desplazamiento(vel_corr_x, vel_corr_y, vel_corr_z, data_segmented['time'], "Velocidad Fir 0.05 - 100 (Z) Deriva corregida")

            desp_fig = get_graficas_desplazamiento(desp_x, desp_y, desp_z, data_segmented['time'], "Desplazamiento Fir 0.05 - 100 (Z) Integral sobre velocidad corregida")

            displacement_fir_deriva_acel_fig = get_graficas_desplazamiento(desp_fir_der_acel_x, desp_fir_der_acel_y, desp_fir_der_acel_z, data_segmented['time'], "Desplazamiento Fir 0.05 - 100 (Z) Deriva sobre velocidad y desplazamiento")

            

            #Desplazamiento algoritmo JM con diferente enfoque

            datos = {}

            datos['X'] = vel_data_der_x
            datos['Y'] = vel_data_der_y
            datos['Z'] = vel_data_der_z

            data_vel_fir_filt = apply_fir_filter('bandpass', 0.05, 100, datos, sampling_freq)

            desp_fir_der_acel_x = calculate_displacement_vel_slope(data_vel_fir_filt['X'], data_segmented['time'])
            desp_fir_der_acel_y = calculate_displacement_vel_slope(data_vel_fir_filt['Y'], data_segmented['time'])
            desp_fir_der_acel_z = calculate_displacement_vel_slope(data_vel_fir_filt['Z'], data_segmented['time'])

            data_desp_to_filt = {}

            data_desp_to_filt['X'] = desp_fir_der_acel_x
            data_desp_to_filt['Y'] = desp_fir_der_acel_y
            data_desp_to_filt['Z'] = desp_fir_der_acel_z

            data_desp_fir_filt = apply_fir_filter('bandpass', 0.05, 100, data_desp_to_filt, sampling_freq)

            displacement_fir_deriva_acel_slope_fig_filters = get_graficas_desplazamiento(data_desp_fir_filt['X'], data_desp_fir_filt['Y'], data_desp_fir_filt['Z'], data_segmented['time'], "Desplazamiento FIR(801) 0.1 - 100 (X, Y, Z) JM - Slope - Filtro")

            #Desplazamiento por superposición de PSD

            displacement_super_psd_x = calculate_displacement_superposition_psd(acceleration= data_segmented['X'], time= data_segmented['time'])
            displacement_super_psd_y = calculate_displacement_superposition_psd(acceleration= data_segmented['Y'], time= data_segmented['time'])
            displacement_super_psd_z = calculate_displacement_superposition_psd(acceleration= data_segmented['Z'], time= data_segmented['time'])

            displacement_super_psd_fig = get_graficas_desplazamiento(displacement_super_psd_x, displacement_super_psd_y, displacement_super_psd_z, data_segmented['time'], "Desplazamiento Superposición Frecuencias Modales (X, Y, Z)")

            return (html.Pre(header_str), fig, fft_fig, psd_fig, velocity_fig, velocity_deriva_acel_fig, displacement_fig, displacement_deriva_acel_fig, displacement_deriva_acel_vel_fig, acel_corr_fig, vel_fig, vel_corr_fig, desp_fig, displacement_fir_deriva_acel_fig, displacement_fir_deriva_acel_slope_fig_filters, displacement_super_psd_fig)

        print("No se ha cargado ningún archivo.")
        return html.Div(['No se ha cargado ningún archivo.']), {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}

    # Callback para manejar la visibilidad del segundo campo de frecuencia
    @app.callback(
        Output('cutoff-frequency-2', 'style'),
        Input('filter-type', 'value')
    )
    def toggle_cutoff_frequency_2(filter_type):
        if filter_type in ['bandpass', 'bandstop']:
            return {'margin-left': '10px', 'display': 'inline-block'}
        else:
            return {'margin-left': '10px', 'display': 'none'}
