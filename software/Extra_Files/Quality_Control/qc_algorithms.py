import numpy as np
from scipy.optimize import curve_fit

def gaussian(x, a, x0, sigma, c):
    return a * np.exp(-(x - x0)**2 / (2 * sigma**2)) + c

def fit_gauss_coluna_janela(
    img_cortada,
    img_norm_cortada,
    x_index,                 # coluna X central
    z=None,                  # índice Z (se 3D); se None, média ao longo de Z
    window_y=200,            # tamanho da janela em Y centrada no pico
    agrupamento=0,           # número de colunas à esquerda/direita para agrupar
    baseline_mode="auto",    # "auto", "min", float ou "none"
    use_scipy=True,          # tenta otimizar com scipy se disponível
    pixel_size_um=None,      # tamanho de pixel em micrómetros
    show_plots=True,         # desenha gráficos
    figsize_profiles=(8, 5),
    figsize_image=(6, 6)
):
    """
    Ajusta um Gaussiano ao perfil médio de uma coluna X (ou grupo de colunas próximas)
    numa janela centrada no pico.

    Modelo: g(y) = b + A * exp(-((y - mu)**2) / (2 * sigma**2))

    Retorna:
        resultados: dict com parâmetros (A, mu, sigma, baseline, FWHM_px, FWHM_um, r2, y0, y1)
        yy_win: np.ndarray (índices Y usados no fit)
        vals_win: np.ndarray (intensidades originais na janela)
        fit_win: np.ndarray (valores do Gaussiano ajustado na janela)
    """
    # --- Preparar imagem 2D ---
    if img_cortada.ndim == 3:
        Z, Y, X = img_cortada.shape
        if z is None:
            img2d = img_cortada.mean(axis=0)
            z_info = " (média em Z)"
        else:
            if not (0 <= z < Z):
                raise IndexError(f"Índice Z fora dos limites: z={z}, permitido 0..{Z-1}")
            img2d = img_cortada[z]
            z_info = f" (Z={z})"
    elif img_cortada.ndim == 2:
        Y, X = img_cortada.shape
        img2d = img_cortada
        z_info = ""
    else:
        raise ValueError(f"Esperado img_cortada 2D ou 3D. Recebido shape: {img_cortada.shape}")

    # --- Verificações ---
    if not (0 <= x_index < X):
        raise IndexError(f"Coluna X fora dos limites: {x_index}, permitido 0..{X-1}")
    if window_y < 5:
        raise ValueError("window_y demasiado pequeno; usa pelo menos 5.")
    if agrupamento < 0:
        raise ValueError("agrupamento deve ser >= 0.")

    # --- Definir intervalo de colunas para agrupar ---
    x0 = max(0, x_index - agrupamento)
    x1 = min(X, x_index + agrupamento + 1)

    # Perfil médio das colunas selecionadas
    perfil = img2d[:, x0:x1].mean(axis=1).astype(np.float64)

    # --- Localizar pico e definir janela ---
    y_peak = int(np.argmax(perfil))
    half = window_y // 2
    y0 = max(0, y_peak - half)
    y1 = min(Y, y_peak + half)
    if (y1 - y0) < 5:
        y0 = max(0, y_peak - 2)
        y1 = min(Y, y_peak + 3)

    yy_win = np.arange(y0, y1)
    vals_win = perfil[y0:y1]

    # --- Estimar baseline ---
    if isinstance(baseline_mode, (int, float)):
        b_est = float(baseline_mode)
    elif baseline_mode == "auto":
        b_est = np.percentile(vals_win, 10)
    elif baseline_mode == "min":
        b_est = float(np.min(vals_win))
    elif baseline_mode == "none":
        b_est = 0.0
    else:
        raise ValueError("baseline_mode inválido.")

    vals_pos = np.clip(vals_win - b_est, a_min=0.0, a_max=None)

    # --- Estimativas iniciais ---
    if np.all(vals_pos == 0):
        A0 = 0.0
        mu0 = float(y_peak)
        sigma0 = max(1.0, window_y / 10.0)
    else:
        A0 = float(vals_pos.max())
        mu0 = float(np.average(yy_win, weights=vals_pos))
        sigma0 = float(np.sqrt(np.average((yy_win - mu0)**2, weights=vals_pos)))
        sigma0 = max(sigma0, 1.0)

    # --- Ajuste Gaussiano ---
    def gauss(y, A, mu, sigma, b):
        return b + A * np.exp(-((y - mu)**2) / (2.0 * sigma**2 + 1e-12))

    A_fit, mu_fit, sigma_fit, b_fit = A0, mu0, sigma0, b_est
    used_scipy = False
    if use_scipy:
        try:
            from scipy.optimize import curve_fit
            p0 = [max(A0, 0.0), mu0, max(sigma0, 1e-3), b_est]
            bounds = ([0.0, y0, 1e-3, -np.inf], [np.inf, y1, np.inf, np.inf])
            popt, _ = curve_fit(gauss, yy_win, vals_win, p0=p0, bounds=bounds, maxfev=10000)
            A_fit, mu_fit, sigma_fit, b_fit = map(float, popt)
            used_scipy = True
        except Exception:
            used_scipy = False

    # --- Métricas ---
    fit_win = gauss(yy_win, A_fit, mu_fit, sigma_fit, b_fit)
    ss_res = float(np.sum((vals_win - fit_win)**2))
    ss_tot = float(np.sum((vals_win - np.mean(vals_win))**2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    fwhm_px = float(2.0 * np.sqrt(2.0 * np.log(2.0)) * sigma_fit)
    fwhm_um = float(fwhm_px * pixel_size_um) if pixel_size_um is not None else None

    resultados = {
        "A": A_fit,
        "mu": mu_fit,
        "sigma": sigma_fit,
        "baseline": b_fit,
        "FWHM_px": fwhm_px,
        "FWHM_um": fwhm_um,
        "r2": r2,
        "y_peak": y_peak,
        "y0": int(y0),
        "y1": int(y1),
        "x_range": (x0, x1-1),
        "used_scipy": used_scipy,
    }

    # --- Visualização ---
    if show_plots:
        plt.figure(figsize=figsize_profiles)
        plt.plot(np.arange(Y), perfil, color='gray', alpha=0.3, label=f"Perfil médio X={x0}..{x1-1}")
        plt.plot(yy_win, vals_win, 'o', ms=4, color='tab:blue', label="Dados na janela")
        plt.plot(yy_win, fit_win, '-', lw=2, color='tab:red', label="Fit Gaussiano")
        plt.axvline(y0, color='k', ls='--', alpha=0.3)
        plt.axvline(y1-1, color='k', ls='--', alpha=0.3)
        txt = f"mu={mu_fit:.1f}px, σ={sigma_fit:.1f}px, FWHM={fwhm_px:.1f}px"
        if fwhm_um is not None:
            txt += f" ({fwhm_um:.2f} µm)"
        txt += f"\nR²={r2:.3f}" if not np.isnan(r2) else ""
        plt.title(f"Fit Gaussiano em colunas X={x0}..{x1-1}{z_info}\n{txt}")
        plt.xlabel("Índice Y (pixels)")
        plt.ylabel("Intensidade média")
        plt.legend()
        plt.grid(alpha=0.25)
        plt.tight_layout()
        plt.show()

        plt.figure(figsize=figsize_image)
        if img_norm_cortada.ndim == 3:
            plt.imshow(img_norm_cortada[img_norm_cortada.shape[0] // 2], cmap='gray')
        else:
            plt.imshow(img_norm_cortada, cmap='gray')
        plt.axvline(x_index, color='cyan', lw=1.2, alpha=0.8)
        plt.axvline(x0, color='yellow', lw=1.0, ls='--', alpha=0.8)
        plt.axvline(x1-1, color='yellow', lw=1.0, ls='--', alpha=0.8)
        plt.axhline(y0, color='yellow', lw=1.0, ls='--', alpha=0.8)
        plt.axhline(y1-1, color='yellow', lw=1.0, ls='--', alpha=0.8)
        plt.title("Imagem normalizada com janela e colunas agrupadas")
        plt.tight_layout()
        plt.show()

    return resultados, yy_win, vals_win, fit_win

#------------------------------------------------------------------------------------------------------------------------------

def extract_gaussian_profiles(
    image: np.ndarray,
    num_points: int,
    beam_window: int,
    agrupamento: int,
    *,
    baseline_mode="auto",
    use_scipy=True,
    min_r2=0.7,
    pixel_size_um=None,
):
    """
    Aplica fit_gauss_coluna_janela a várias colunas da imagem.

    Retorna:
        cols  : np.ndarray (X usados)
        peaks : np.ndarray (mu em pixels Y)
        fwhms : np.ndarray (FWHM em pixels)
        r2s   : np.ndarray (qualidade do fit)
    """

    if image.ndim not in (2, 3):
        raise ValueError("Imagem deve ser 2D ou 3D")

    if image.ndim == 3:
        _, Y, X = image.shape
    else:
        Y, X = image.shape

    # Seleção uniforme das colunas X
    cols = np.linspace(0, X - 1, num_points).astype(int)

    used_cols = []
    peaks = []
    fwhms = []
    r2s = []

    for x in cols:
        try:
            resultados, _, _, _ = fit_gauss_coluna_janela(
                img_cortada=image,
                img_norm_cortada=image,
                x_index=x,
                window_y=beam_window,
                agrupamento=agrupamento,
                baseline_mode=baseline_mode,
                use_scipy=use_scipy,
                pixel_size_um=pixel_size_um,
                show_plots=False,   # 🔴 obrigatório em QC contínuo
            )
        except Exception:
            continue

        r2 = resultados.get("r2", np.nan)
        if not np.isfinite(r2) or r2 < min_r2:
            continue

        used_cols.append(x)
        peaks.append(resultados["mu"])
        
        if pixel_size_um is not None and resultados.get("FWHM_um") is not None:
            fwhms.append(resultados["FWHM_um"])
        else:
            fwhms.append(resultados["FWHM_px"])

        r2s.append(r2)

    return (
        np.asarray(used_cols),
        np.asarray(peaks),
        np.asarray(fwhms),
        np.asarray(r2s),
    )


def calculate_tilt_from_peaks(cols, peaks):
    """
    Ajusta uma reta aos picos (Y) em função das colunas (X)
    e devolve o ângulo do tilt.
    """

    if len(cols) < 2:
        return np.nan, None

    coef = np.polyfit(cols, peaks, 1)
    slope = coef[0]

    angle_rad = np.arctan(slope)
    angle_deg = np.degrees(angle_rad)

    return angle_deg, coef


# --- Hiperbole FWHM (foco) ---------------------------------------------------
import numpy as np

def _hiperbola_model(x, a, b, c, f):
    # y = b * sqrt((x - f)^2 + a^2) + c
    return b * np.sqrt((x - f)**2 + a**2) + c

def _initial_guess_hyperbola(x, y):
    """
    Estima chute inicial robusto:
    - f0: posição de menor y
    - a0: escala ~ 0.25 * faixa de x (>= 1e-6)
    - b0, c0: via regressão linear sobre s = sqrt((x-f0)^2 + a0^2)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # remove NaNs/inf
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]; y = y[m]
    if len(x) == 0:
        # fallback trivially
        return 1.0, 1.0, float(np.nanmean(y)), float(np.nanmean(x))

    idx_min = np.argmin(y)
    f0 = float(x[idx_min])

    xr = float(np.max(x) - np.min(x))
    a0 = max(1e-6, 0.25 * xr if xr > 0 else 1.0)

    s0 = np.sqrt((x - f0)**2 + a0**2)
    A = np.column_stack([s0, np.ones_like(s0)])
    b0, c0 = np.linalg.lstsq(A, y, rcond=None)[0]

    if b0 < 0:
        b0 = abs(b0)
        c0 = float(np.mean(y - b0 * s0))

    return float(a0), float(b0), float(c0), float(f0)

def _fit_hyperbola_scipy(x, y, p0=None):
    """
    Tenta ajustar com SciPy; devolve (a,b,c,f) ou None.
    """
    try:
        from scipy.optimize import curve_fit
    except Exception:
        return None  # SciPy indisponível

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]; y = y[m]
    if len(x) < 3:
        return None

    if p0 is None:
        a0, b0, c0, f0 = _initial_guess_hyperbola(x, y)
    else:
        a0, b0, c0, f0 = p0

    xmin, xmax = float(np.min(x)), float(np.max(x))
    pad = 0.25 * (xmax - xmin) if xmax > xmin else 1.0
    bounds_lower = [1e-9, 0.0, -np.inf, xmin - pad]
    bounds_upper = [np.inf, np.inf,  np.inf, xmax + pad]

    try:
        popt, _ = curve_fit(
            _hiperbola_model, x, y,
            p0=[a0, b0, c0, f0],
            bounds=(bounds_lower, bounds_upper),
            maxfev=20000
        )
        # garante domínios válidos
        a, b, c, f = map(float, popt)
        a = max(a, 1e-9)
        b = max(b, 0.0)
        return a, b, c, f
    except Exception:
        return None

def _fit_hyperbola_grid(x, y, n_f=101, n_a=61):
    """
    Fallback sem SciPy:
    - Faz grelha em f (dentro da faixa de x) e a (escala positiva)
    - Para cada (a, f), resolve (b, c) por LS e rejeita b < 0
    - Refina localmente ao redor do melhor (a, f)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]; y = y[m]
    if len(x) < 3:
        # Caso extremo: usa chute inicial
        return _initial_guess_hyperbola(x, y)

    xmin, xmax = float(np.min(x)), float(np.max(x))
    xr = xmax - xmin
    if xr <= 0:
        xr = 1.0

    f_grid = np.linspace(xmin, xmax, n_f)
    a_grid = np.linspace(1e-6, 0.75 * xr, n_a)

    best = {"sse": np.inf, "a": None, "b": None, "c": None, "f": None}

    def solve_bc(s, y):
        A = np.column_stack([s, np.ones_like(s)])
        b, c = np.linalg.lstsq(A, y, rcond=None)[0]
        return float(b), float(c)

    for f in f_grid:
        for a in a_grid:
            s = np.sqrt((x - f)**2 + a**2)
            b, c = solve_bc(s, y)
            if b < 0:
                continue
            resid = y - (b * s + c)
            sse = float(np.dot(resid, resid))
            if sse < best["sse"]:
                best.update({"sse": sse, "a": a, "b": b, "c": c, "f": f})

    # Refinamento
    if best["a"] is not None:
        a0, f0 = best["a"], best["f"]
        a_ref = np.linspace(max(1e-6, a0 * 0.5), a0 * 1.5, 41)
        f_ref = np.linspace(f0 - 0.2 * xr, f0 + 0.2 * xr, 41)
        for f in f_ref:
            for a in a_ref:
                s = np.sqrt((x - f)**2 + a**2)
                b, c = solve_bc(s, y)
                if b < 0:
                    continue
                resid = y - (b * s + c)
                sse = float(np.dot(resid, resid))
                if sse < best["sse"]:
                    best.update({"sse": sse, "a": a, "b": b, "c": c, "f": f})

        return best["a"], best["b"], best["c"], best["f"]

    # fallback final
    return _initial_guess_hyperbola(x, y)

def fit_focus_hyperbola(cols, fwhms, *, use_scipy=True):
    """
    Envolve o ajuste hiperbólico para FWHM(x).
    Retorna dict com parâmetros e y_min.
    """
    x = np.asarray(cols, dtype=float)
    y = np.asarray(fwhms, dtype=float)

    # se houver poucos pontos válidos, falha
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]; y = y[m]
    if len(x) < 3:
        return {"ok": False}

    p0 = _initial_guess_hyperbola(x, y)
    popt = _fit_hyperbola_scipy(x, y, p0=p0) if use_scipy else None
    if popt is None:
        popt = _fit_hyperbola_grid(x, y)
    a, b, c, f = map(float, popt)
    a = max(a, 1e-9); b = max(b, 0.0)
    y_min = b * a + c

    return {"ok": True, "a": a, "b": b, "c": c, "f": f, "y_min": y_min}
# -----------------------------------------------------------------------------


def calculate_focus_point(cols, fwhms, peaks, *, method="hyperbola", use_scipy=True, tilt_coef=None):
    """
    Determina o ponto de melhor foco.
    - method="hyperbola": usa ajuste hiperbólico a FWHM(x) e toma x=f como foco.
      Se tilt_coef=(m, b) for fornecido, estima row = m*f + b; caso contrário
      usa o pico mais próximo de f.
    - fallback: se falhar, usa mínimo direto de fwhms.
    """
    cols = np.asarray(cols)
    fwhms = np.asarray(fwhms)
    peaks = np.asarray(peaks)

    if len(fwhms) == 0 or len(cols) == 0:
        return None

    if method == "hyperbola":
        fit = fit_focus_hyperbola(cols, fwhms, use_scipy=use_scipy)
        if fit.get("ok", False):
            f = float(fit["f"])       # coluna contínua do foco
            fwhm_min = float(fit["y_min"])
            # linha (row) no foco:
            if tilt_coef is not None and np.all(np.isfinite(tilt_coef)):
                m, b = tilt_coef
                row_at_f = float(m * f + b)
            else:
                # usa pico mais próximo
                idx_near = int(np.argmin(np.abs(cols - f)))
                row_at_f = float(peaks[idx_near])

            return {
                "column": int(np.round(f)),   # compatibilidade com inteiro
                "column_float": f,            # valor contínuo do foco (x=f)
                "row": row_at_f,              # estimativa de Y no foco
                "fwhm": fwhm_min,             # FWHM mínimo previsto
                "fit_params": {"a": fit["a"], "b": fit["b"], "c": fit["c"], "f": fit["f"]},
                "method": "hyperbola",
            }

    # --- fallback clássico: mínimo nos dados discretos ---
    idx = int(np.argmin(fwhms))
    return {
        "column": int(cols[idx]),
        "column_float": float(cols[idx]),
        "row": float(peaks[idx]),
        "fwhm": float(fwhms[idx]),
        "fit_params": None,
        "method": "argmin",
    }


#-----------------------------------------------------------------------------------------

#Run all in one time(to use with only a button)

def run_qc_analysis(
    image,
    *,
    num_points,
    beam_window,
    agrupamento,
    min_r2=0.7,
):
    """
    Executa QC completo num único frame.
    """

    cols, peaks, fwhms, r2s = extract_gaussian_profiles(
        image=image,
        num_points=num_points,
        beam_window=beam_window,
        agrupamento=agrupamento,
        min_r2=min_r2,
    )

    if len(cols) < 5:
        return None

    angle, coef = calculate_tilt_from_peaks(cols, peaks)
    focus = calculate_focus_point(cols, fwhms, peaks)

    return {
        "cols": cols,
        "peaks": peaks,
        "fwhms": fwhms,
        "r2s": r2s,
        "angle": angle,
        "tilt_coef": coef,
        "focus": focus,
    }

#----------------------------------------------------------------------------------------------------
