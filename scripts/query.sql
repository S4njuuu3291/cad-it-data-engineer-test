-- a. Number of unique film titles
SELECT unique_film_titles
FROM vw_unique_film_titles;

-- b. Film Title, Year of Release, and Rating of the film starring Lena Headey Sort By Year of Release.
SELECT film_title, year_of_release, rating
FROM vw_lena_headey_films
ORDER BY year_of_release;

-- c. The name of the director and total gross of the films that have been directed.
SELECT director_name, total_gross
FROM vw_director_total_gross
ORDER BY total_gross DESC NULLS LAST;

-- d. Film Title, Year of Release, and Rating of 5 films that have comedy genre with the largest gross
SELECT film_title, year_of_release, rating
FROM vw_top5_comedy_films
ORDER BY gross DESC, film_title;

-- e. Film Title, Year of Release and Rating of the film directed by Martin Scorsese and starring Robert De Niro
SELECT film_title, year_of_release, rating
FROM vw_scorsese_de_niro_films
ORDER BY year_of_release;
