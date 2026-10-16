CREATE TABLE titles (
    title_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(500),
    release_start_year SMALLINT,
    release_end_year SMALLINT,
    rating NUMERIC(3, 1),
    votes INTEGER,
    synopsis TEXT,
    runtime_minutes INTEGER,
    gross NUMERIC(18, 2),
    CHECK (rating BETWEEN 0 AND 10),
    CHECK (votes >= 0),
    CHECK (runtime_minutes > 0),
    CHECK (gross >= 0),
    CHECK (release_end_year >= release_start_year)
);

CREATE TABLE genres (
    genre_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    genre_name VARCHAR(100) UNIQUE
);

CREATE TABLE persons (
    person_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    person_name VARCHAR(255)
);

CREATE TABLE title_genres (
    title_id BIGINT REFERENCES titles (title_id),
    genre_id BIGINT REFERENCES genres (genre_id),
    PRIMARY KEY (title_id, genre_id)
);

CREATE TABLE credits (
    credit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title_id BIGINT NOT NULL REFERENCES titles (title_id),
    person_id BIGINT NOT NULL REFERENCES persons (person_id),
    role VARCHAR(30)
);
