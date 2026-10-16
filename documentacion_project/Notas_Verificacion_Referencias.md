# Notas de verificación de referencias y contenido

Documento de apoyo a `Documento_IEEE_Control_Gestual.md`. No forma parte del texto IEEE.
Fecha de verificación: 15 de octubre de 2026.

## 1. Origen y verificación de cada referencia

| N.º | Referencia | Origen | Verificación |
|---|---|---|---|
| [1] | Wachs *et al.*, JAMIA 2008 | Añadida | Registro de Europe PMC (PMID 18451034): autores, título, vol. 15, n.º 3, pp. 321–323 y resumen coinciden |
| [2] | Mewes *et al.*, IJCARS 2017 | Añadida | Registro de Europe PMC (PMID 27647327): autores, vol. 12, n.º 2, pp. 291–305; las cifras 55 / 14.5 % / 12.7 % salen del resumen |
| [3] | Zhang *et al.*, MediaPipe Hands | Añadida | Página de arXiv:2006.10214 y texto completo leídos |
| [4] | Lugaresi *et al.*, MediaPipe | Añadida | Página de arXiv:1906.08172 leída (resumen); la lista completa de autores no se extrajo, por eso se cita "*et al.*" |
| [5] | Google, Hand landmarks detection guide | Propuesta del equipo (título corregido) | URL accesible; título real de la página: "Hand landmarks detection guide" (la propuesta decía "Hand landmarker guide"). Solo se extrajo el título, no el cuerpo |
| [6] | MediaPipe Hands (legacy) | Añadida | Texto leído: indica que el 1 de marzo de 2023 la solución pasó a una nueva solución |
| [7] | Casiez, Roussel, Vogel, CHI 2012 | Propuesta del equipo | Página del autor (gery.casiez.net/1euro) confirma título, CHI '12, Austin, pp. 2527–2530 y DOI 10.1145/2207676.2208639. También confirma el procedimiento de ajuste en dos pasos |
| [8] | Rashad, blog Free Face MoCap | Propuesta del equipo (título corregido) | Página accesible; su título real es "OneEuro Filter" (la URL termina en `filters-for-stability`). Fecha 25-dic-2021 según el índice de la propia página |
| [9] | Bradski, OpenCV, Dr. Dobb's 2000 | Añadida | Vol. 25, n.º 11, pp. 120–125 según fuentes secundarias; no se consultó el original |
| [10] | Harris *et al.*, NumPy, Nature 2020 | Añadida | Vol. 585, pp. 357–362 y DOI según fuentes secundarias consistentes |
| [11] | Sweigart, PyAutoGUI | Añadida | Documentación leída: fail-safe activo por defecto en las 4 esquinas y demora de 0.1 s tras cada función |
| [12] | Píldoras de programación (video) | Propuesta del equipo | La existencia y el contenido (MediaPipe + OpenCV + detección de manos) se confirmaron por búsqueda. **La página de YouTube no se pudo leer**; el título y la fecha son los de la propuesta |
| [13] | La Cascia *et al.*, TPAMI 2000 | Propuesta del equipo (**corregida**) | Ver sección 2 |
| [14] | Google, Face landmark detection guide | Propuesta del equipo | URL accesible; título real: "Face landmark detection guide" |
| [15] | Hincapié-Ramos *et al.*, CHI 2014 | Añadida (fatiga de brazo) | Verificada en ACM Digital Library (DOI 10.1145/2556288.2557130): autores (J. D. Hincapié-Ramos, X. Guo, P. Moghadasian, P. Irani), título ("Consumed endurance: A metric to quantify arm fatigue of mid-air interactions"), CHI '14, Toronto, pp. 1063–1072 |
| [16] | Chatterjee, Xiao, Harrison, ICMI 2015 | Añadida (*Gaze+Gesture*) | Verificada en ACM Digital Library (DOI 10.1145/2818346.2820752): autores (I. Chatterjee, R. Xiao, C. Harrison), título ("Gaze+Gesture: Expressive, precise and targeted free-space interactions"), ICMI '15, Seattle, pp. 131–138 |
| [17] | Pfeuffer *et al.*, SUI 2017 | Añadida (*Gaze + Pinch*) | Verificada en ACM Digital Library (DOI 10.1145/3131277.3132180): autores (K. Pfeuffer, B. Mayer, D. Mardanbegi, H. Gellersen), título ("Gaze + pinch interaction in virtual reality"), SUI '17, Brighton, pp. 99–108 |

Las referencias marcadas "Añadida" no estaban en la propuesta. Se incorporaron porque sustentan afirmaciones que el documento hace (contexto clínico, modelo de MediaPipe, librerías usadas y mitigación ergonómica de la fatiga del brazo mediante *Gaze + Pinch*). Si alguna no corresponde a lo que el equipo consultó realmente, puede eliminarse junto con la frase que la cita.

## 2. Errores detectados en la bibliografía de la propuesta

**La Cascia, Sclaroff y Athitsos.** La propuesta dice:
"Fast, reliable head tracking under large head rotation: A active appearance model-based approach", TPAMI vol. 22, no. 6, pp. 588–599.

Los datos verificados son:
"Fast, reliable head tracking under varying illumination: An approach based on registration of texture-mapped 3D models", TPAMI vol. 22, no. 4, pp. 322–336, abril de 2000, DOI 10.1109/34.845375.

El título, el número, las páginas y la descripción del método ("active appearance model") eran incorrectos. La propia URL de la propuesta (`pami.22.4.pdf`) apuntaba al número 4. **Conviene corregir la propuesta.**

## 3. Afirmaciones del proyecto sin respaldo verificable

- **Tabla "Evaluación Experimental Comparativa" del README** (28.4 px → 0.0 px, 18.2 % → 0.0 %, etc.): no hay datos ni scripts en el repositorio. Se omitió del documento.
- **"Las mascarillas y gorros degradan Face Mesh":** aparece en `docs/` sin cita. Se presentó como hipótesis de diseño. Si el equipo quiere sostenerla, necesita una referencia (por ejemplo, un estudio sobre reconocimiento facial con mascarillas).
- **"A 30 FPS la mano no salta más de 150 px":** supuesto no medido.
- **Ventaja del modo gestual frente al ocular en quirófano:** no probada.

## 4. Discrepancias entre documentación y código

| Tema | Documentación | Código / ejecución |
|---|---|---|
| Soporte 3D (*world landmarks*) | README y encabezado de `gesture_controller.py` | El parámetro se recibe pero no se usa |
| Pruebas del controlador | README: 29 | 36 (incluyendo integración híbrida y pinza relajada) |
| Insignia de pruebas | README: 39 | 72 totales (ejecutado: 36 + 18 + 10 + 8) |
| Timeout de pausa | "10 s sin actividad" | 10 s desde que inicia la pausa |
| Reactivación desde pausa (1.0 s) | README y spec | **Corregido** en `user_lock.py` (`self._activation_start_time = None` al entrar en `ACTIVO`) |

## 5. Limitaciones de este trabajo de documentación

- `documentacion_project/Proyecto_Semestral.docx` no se pudo abrir (error "Directorio central dañado" al leerlo como ZIP, posiblemente un marcador de posición de OneDrive no sincronizado). Si contiene la plantilla o los requisitos de la entrega, hay que revisarlos manualmente.
- Las cifras de las pruebas provienen de una ejecución real (`Ran 72 tests — OK`, Python 3.12.10).

