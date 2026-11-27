# Resultados de las pruebas de consultas

Ejecutadas con `python3 pruebas/probar_consultas.py` el 2026-11-27 contra el core `crimen` de Solr.

**Resultado: 16 de 19 pruebas pasan.**

| # | Prueba | Qué verifica | Resultado obtenido | Estado |
|---|---|---|---|---|
| 1 | Indexación completa | La cantidad de documentos en Solr es igual a la cantidad de líneas del archivo generado por el ETL. | archivo: 240 683, Solr: 240 683 | PASA |
| 2 | Todos los documentos tienen ubicación | Ningún documento queda sin valor en el campo espacial ubicacion. | documentos sin ubicación: 0 | PASA |
| 3 | Operador AND frente a filtros fq | Unir dos condiciones con AND en q da la misma cantidad que enviarlas como dos fq. | q con AND: 8 280, dos fq: 8 280 | PASA |
| 4 | Operador OR | Como un delito pertenece a un solo cantón, el OR de dos cantones suma los delitos de ambos. | Garabito: 5 242 + Quepos: 3 385 = OR: 8 627 | PASA |
| 5 | Operador NOT | Los registros con una condición más los registros con su negación dan el total. | COSTA RICA: 4 679 + NOT COSTA RICA: 1 050 = total: 5 729 | PASA |
| 6 | Búsqueda de texto libre | Buscar la palabra 'taxista' en el campo de texto encuentra al menos los registros cuya subvíctima es TAXISTA. | texto:taxista: 957, subvictima TAXISTA: 957 | PASA |
| 7 | Rango temporal | El rango de fechas de 2020 devuelve lo mismo que el campo anio = 2020. | rango de fechas: 24 911, anio:2020: 24 911 | PASA |
| 8 | Rango numérico | Los rangos [6 TO *] y [* TO 6} se complementan: juntos suman el total (la llave } excluye el 6). | desempleo >= 6: 0 + desempleo < 6: 240 683 = 240 683 | PASA |
| 9 | Ordenamiento por dos atributos | En los primeros 200 resultados, la tasa de desempleo nunca sube y, cuando empata, la fecha nunca sube. | documentos revisados: 200 | PASA |
| 10 | Field facet | La suma de los conteos del facet por tipo de delito es igual al total de documentos. | suma del facet: 240 683, total: 240 683 | PASA |
| 11 | Range facet | La suma de los intervalos anuales de 2019 a 2026 es igual al total de documentos. | suma de los intervalos: 240 683, total: 240 683 | PASA |
| 12 | Facet anidado | En cada tipo de economía, la suma de los subgrupos por delito es igual al conteo del grupo. | grupos revisados: 2 | PASA |
| 13 | Facet con funciones estadísticas | La tasa de desempleo es un dato del cantón, así que en cada cantón del censo el mínimo y el máximo coinciden. | cantones revisados: 81, cantones con mínimo distinto del máximo: 0 | PASA |
| 14 | Proximidad: puntos dentro del radio | Todos los puntos devueltos por una búsqueda de 5 km alrededor del centro de San José están a 5 km o menos (distancia calculada aparte con la fórmula de Haversine). | encontrados: 53 050, distancia máxima revisada: 5.142 km | FALLA |
| 15 | Proximidad: radio mayor contiene al menor | Un radio de 10 km encuentra al menos los mismos delitos que uno de 5 km. | 5 km: 53 050, 10 km: 83 162 | PASA |
| 16 | Polígono: puntos dentro del área | Ninguno de los puntos devueltos por un polígono rectangular sobre San José queda fuera del rectángulo. | encontrados: 73 466, revisados: 5000, fuera del área: 53 | FALLA |
| 17 | Polígono real del cantón Montes de Oca | La consulta con el polígono del cantón (1220 vértices) recupera todos sus delitos. | delitos del cantón: 5 404, recuperados: 5 404, de cantones vecinos: 895 (14.21 %) | FALLA |
| 18 | Polígono real del cantón San Pablo | La consulta con el polígono del cantón (230 vértices) recupera todos sus delitos. | delitos del cantón: 894, recuperados: 894, de cantones vecinos: 16 (1.76 %) | PASA |
| 19 | Polígono real del cantón San Jose | La consulta con el polígono del cantón (2967 vértices) recupera todos sus delitos. | delitos del cantón: 57 595, recuperados: 57 595, de cantones vecinos: 629 (1.08 %) | PASA |
