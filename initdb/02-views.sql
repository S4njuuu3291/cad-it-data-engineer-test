-- a. Number of distinct title names.
CREATE OR REPLACE VIEW vw_unique_film_titles AS
SELECT COUNT(DISTINCT name) AS unique_film_titles
FROM titles;

-- b. Titles starring Lena Headey.
CREATE OR REPLACE VIEW vw_lena_headey_films AS
SELECT t.name AS film_title, t.release_start_year AS year_of_release, t.rating
FROM titles t
JOIN credits c ON t.title_id = c.title_id
JOIN persons p ON c.person_id = p.person_id
WHERE p.person_name = 'Lena Headey'
  AND c.role = 'actor';

-- c. Total known gross per director; unknown totals remain NULL.
CREATE OR REPLACE VIEW vw_director_total_gross AS
SELECT p.person_name AS director_name, SUM(t.gross) AS total_gross
FROM titles t
JOIN credits c ON t.title_id = c.title_id
JOIN persons p ON c.person_id = p.person_id
WHERE c.role = 'director'
GROUP BY p.person_name;

-- d. Gross is exposed so callers can order the five selected films.
CREATE OR REPLACE VIEW vw_top5_comedy_films AS
SELECT t.name AS film_title, t.release_start_year AS year_of_release, t.rating, t.gross
FROM titles t
JOIN title_genres tg ON t.title_id = tg.title_id
JOIN genres g ON tg.genre_id = g.genre_id
WHERE g.genre_name = 'Comedy'
  AND t.gross IS NOT NULL
ORDER BY t.gross DESC, t.title_id
LIMIT 5;

-- e. Titles directed by Martin Scorsese and starring Robert De Niro.
CREATE OR REPLACE VIEW vw_scorsese_de_niro_films AS
SELECT t.name AS film_title, t.release_start_year AS year_of_release, t.rating
FROM titles t
JOIN credits c1 ON t.title_id = c1.title_id
JOIN persons p1 ON c1.person_id = p1.person_id
JOIN credits c2 ON t.title_id = c2.title_id
JOIN persons p2 ON c2.person_id = p2.person_id
WHERE c1.role = 'director' AND p1.person_name = 'Martin Scorsese'
  AND c2.role = 'actor' AND p2.person_name = 'Robert De Niro';
