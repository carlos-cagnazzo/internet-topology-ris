# Lab Notebook

## 12 de abril 

  - ahora con los scripts que procesan tambien los archivos de updates estoy corriendo para los dias del mes de abril de 2025
  - inicialmente veo que efectivamente hay ases que aparecen unos dias si y otros no 
    - entre 1 y 30 de abril hay 509 que estan en uno de los dias y 609 que estan en el otro pero no en el primero

## 17 de abril

  - el pipeline se está corriendo en paralelo en varias máquinas (jordan, yacare, atl01, gauss, euler) para acelerar el procesamiento
  - se creó `fetch-results.sh` para consolidar los resultados: hace rsync de cada máquina remota a `./fetch/<hostname>/` para evitar conflictos entre archivos del mismo nombre
    - incluye `topology-YYYYMMDD.txt` (edge list) y `topology-YYYYMMDD-asns.txt` por defecto
    - para contar ASes únicos en los archivos consolidados: `zcat fetch/*/topology-????????.txt | awk '{print $1; print $2}' | sort -un | wc -l`
