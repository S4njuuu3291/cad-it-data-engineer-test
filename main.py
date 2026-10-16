import logging
import os
import re
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import MetaData, URL, create_engine, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

DATASET_PATH = "material/movies.csv"
TABLE_NAMES = ("titles", "genres", "persons", "title_genres", "credits")
logger = logging.getLogger(__name__)


def raise_validation_errors(errors, stage):
    if errors:
        logger.error("Validasi %s gagal: %s pelanggaran", stage, len(errors))
        for error in errors[:10]:
            logger.error("%s", error)
        raise ValueError(f"Validasi {stage} gagal: {len(errors)} pelanggaran")


def convert_number(values, column, integer=False):
    try:
        numbers = pd.to_numeric(values)
        if numbers.isin([float("inf"), float("-inf")]).any():
            raise ValueError("Angka tidak boleh infinity")
        if integer and column == "RunTime":
            numbers = numbers.map(lambda value: int(value) if pd.notna(value) else pd.NA)
        return numbers.astype("Int64" if integer else "Float64")
    except (ValueError, TypeError, OverflowError) as error:
        logger.error("Konversi kolom %s gagal: %s", column, error)
        raise


def extract(path=DATASET_PATH):
    """Baca CSV dengan pandas, lalu teruskan records lewat memori."""
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except FileNotFoundError:
        logger.error("File CSV tidak ditemukan: %s", path)
        return None
    except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError):
        logger.exception("Gagal membaca CSV: %s", path)
        return None

    records = frame.to_dict(orient="records")
    logger.info("Ekstrak selesai: %s baris dari %s", len(records), path)
    return records


def transform(records):
    """Bersihkan records dengan pandas, lalu bentuk payload untuk lima tabel."""
    frame = pd.DataFrame(records)
    if frame.empty:
        logger.error("Data untuk transformasi kosong")
        return {table: [] for table in TABLE_NAMES}

    required = {"MOVIES", "YEAR", "GENRE", "RATING", "ONE-LINE", "STARS", "VOTES", "RunTime", "Gross"}
    missing = sorted(required - set(frame.columns))
    raise_validation_errors([f"Kolom sumber tidak tersedia: {column}" for column in missing], "kolom sumber")

    original_count = len(frame)
    frame = frame.drop_duplicates(keep="first").copy()
    logger.info("Duplikat dihapus: %s baris", original_count - len(frame))

    columns = ["MOVIES", "YEAR", "GENRE", "RATING", "VOTES", "RunTime", "Gross"]
    for column in columns:
        frame[column] = frame[column].astype("string").str.strip().replace("", pd.NA)

    year_text = frame.pop("YEAR")
    years = year_text.str.findall(r"\b\d{4}\b")
    start = pd.to_numeric(years.str[0]).astype("Int64")
    end = pd.to_numeric(years.str[1]).astype("Int64").fillna(start)
    open_range = year_text.str.contains(r"\d{4}\s*[–-]", na=False) & years.str.len().eq(1)
    frame["release_start_year"] = start
    frame["release_end_year"] = end.mask(open_range)

    frame["GENRE"] = frame["GENRE"].str.split(r"\s*,\s*").map(
        lambda items: ([item for item in items if item] or None)
        if isinstance(items, list)
        else None
    )
    frame["RATING"] = convert_number(frame["RATING"], "RATING")
    frame["VOTES"] = convert_number(frame["VOTES"].str.replace(",", "", regex=False), "VOTES", integer=True)
    frame["RunTime"] = convert_number(frame["RunTime"], "RunTime", integer=True)

    gross = frame["Gross"].str.replace(r"^\$", "", regex=True).str.replace(",", "", regex=False)
    # Nilai CSV dengan akhiran M dinyatakan dalam juta.
    multiplier = gross.str.endswith("M", na=False).map({True: 1_000_000, False: 1})
    frame["Gross"] = (
        convert_number(gross.str.removesuffix("M"), "Gross") * multiplier
    ).astype("Float64")

    logger.info("Transformasi selesai: %s baris", len(frame))
    return build_db_payload(frame)


def build_db_payload(frame):
    """*_ref adalah indeks list induk (mulai 0), bukan ID database.

    Loader harus memetakan referensi ini ke ID hasil INSERT ... RETURNING.
    """
    title_columns = {
        "MOVIES": "name",
        "release_start_year": "release_start_year",
        "release_end_year": "release_end_year",
        "RATING": "rating",
        "VOTES": "votes",
        "ONE-LINE": "synopsis",
        "RunTime": "runtime_minutes",
        "Gross": "gross",
    }
    titles = frame[list(title_columns)].rename(columns=title_columns)
    payload = {
        "titles": [],
        "genres": [],
        "persons": [],
        "title_genres": [],
        "credits": [],
    }
    genre_refs = {}
    person_refs = {}
    title_refs = {}
    row_title_refs = []
    for title in titles.astype(object).where(titles.notna(), None).to_dict(orient="records"):
        key = tuple(title.values())
        if key not in title_refs:
            title_refs[key] = len(payload["titles"])
            payload["titles"].append(title)
        row_title_refs.append(title_refs[key])
    logger.info("Title identik digabung: %s baris", len(titles) - len(payload["titles"]))

    for source_ref, (genres, stars) in enumerate(
        frame[["GENRE", "STARS"]].itertuples(index=False, name=None)
    ):
        title_ref = row_title_refs[source_ref]
        for genre_name in dict.fromkeys(genres or []):
            if genre_name not in genre_refs:
                genre_refs[genre_name] = len(payload["genres"])
                payload["genres"].append({"genre_name": genre_name})
            payload["title_genres"].append({
                "title_ref": title_ref,
                "genre_ref": genre_refs[genre_name],
            })

        if not isinstance(stars, str) or not stars.strip():
            continue
        sections = re.finditer(
            r"\b(Directors?|Stars?):\s*(.*?)(?=\b(?:Directors?|Stars?):|$)",
            stars,
            flags=re.DOTALL,
        )
        for section in sections:
            role = "director" if section.group(1).startswith("Director") else "actor"
            names = section.group(2).strip(" \t\r\n|").split(",")
            for name in names:
                person_name = name.strip()
                if not person_name:
                    continue
                if person_name not in person_refs:
                    person_refs[person_name] = len(payload["persons"])
                    payload["persons"].append({"person_name": person_name})
                payload["credits"].append({
                    "title_ref": title_ref,
                    "person_ref": person_refs[person_name],
                    "role": role,
                })

    for table in ("title_genres", "credits"):
        if payload[table]:
            payload[table] = pd.DataFrame(payload[table]).drop_duplicates().to_dict(orient="records")

    for table, rows in payload.items():
        logger.info("Payload %s: %s baris", table, len(rows))
    return payload


def validate(payload):
    """Cek aturan nilai utama."""
    titles = pd.DataFrame(payload["titles"])
    if titles.empty:
        logger.error("Validasi gagal: data titles kosong")
        raise ValueError("Data titles kosong")

    titles = titles[["rating", "votes", "runtime_minutes", "gross", "release_start_year", "release_end_year"]].apply(pd.to_numeric)
    checks = {
        "rating": titles["rating"].isna() | titles["rating"].between(0, 10),
        "votes": titles["votes"].isna() | titles["votes"].ge(0),
        "runtime_minutes": titles["runtime_minutes"].isna() | titles["runtime_minutes"].gt(0),
        "gross": titles["gross"].isna() | titles["gross"].ge(0),
        "release_end_year": (
            titles["release_start_year"].isna()
            | titles["release_end_year"].isna()
            | titles["release_end_year"].ge(titles["release_start_year"])
        ),
    }
    errors = []
    for column, valid in checks.items():
        valid &= ~titles[column].isin([float("inf"), float("-inf")])
        for index in titles.index[~valid]:
            errors.append(f"titles[{index}].{column}={titles.at[index, column]!r}: nilai tidak valid")
    raise_validation_errors(errors, "nilai titles")
    logger.info("Validasi berhasil")


def create_db_engine():
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")
    password_path = base_dir / os.environ["POSTGRES_PASSWORD_FILE"]
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["POSTGRES_USER"],
        password=password_path.read_text().strip(),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(
        url,
        connect_args={
            "sslmode": "verify-full",
            "sslrootcert": str(base_dir / "certs/ca.crt"),
            "connect_timeout": 10,
        },
        hide_parameters=True,
    )


def load(payload):
    """Full refresh: kosongkan kelima tabel sebelum memasukkan seluruh payload.

    Seluruh batch di-commit bersama; kegagalan membatalkan seluruh batch.
    """
    validate(payload)

    engine = None
    try:
        engine = create_db_engine()
        with engine.begin() as connection:
            metadata = MetaData()
            metadata.reflect(connection, only=list(TABLE_NAMES))
            titles = metadata.tables["titles"]
            genres = metadata.tables["genres"]
            persons = metadata.tables["persons"]

            connection.exec_driver_sql(
                "TRUNCATE TABLE credits, title_genres, persons, genres, titles RESTART IDENTITY"
            )
            logger.info("Kelima tabel dikosongkan dalam transaksi load")

            # Urutan RETURNING harus sama dengan urutan payload untuk *_ref.
            title_ids = connection.execute(
                insert(titles).returning(titles.c.title_id, sort_by_parameter_order=True),
                payload["titles"],
            ).scalars().all()

            genre_ids = []
            if payload["genres"]:
                connection.execute(
                    pg_insert(genres).on_conflict_do_nothing(index_elements=["genre_name"]),
                    payload["genres"],
                )
                names = [row["genre_name"] for row in payload["genres"]]
                genre_map = dict(connection.execute(
                    select(genres.c.genre_name, genres.c.genre_id)
                    .where(genres.c.genre_name.in_(names))
                ).all())
                genre_ids = [genre_map[name] for name in names]

            person_ids = []
            if payload["persons"]:
                names = [row["person_name"] for row in payload["persons"]]
                existing = connection.execute(
                    select(persons.c.person_name, persons.c.person_id)
                    .where(persons.c.person_name.in_(names))
                ).all()
                person_map = dict(existing)
                if len(person_map) != len(existing):
                    raise ValueError("Nama person memiliki beberapa ID di database; pemetaan ambigu")
                missing = [row for row in payload["persons"] if row["person_name"] not in person_map]
                if missing:
                    new_ids = connection.execute(
                        insert(persons).returning(persons.c.person_id, sort_by_parameter_order=True),
                        missing,
                    ).scalars().all()
                    person_map.update(
                        (row["person_name"], person_id)
                        for row, person_id in zip(missing, new_ids)
                    )
                person_ids = [person_map[name] for name in names]

            title_genres = [
                {"title_id": title_ids[row["title_ref"]], "genre_id": genre_ids[row["genre_ref"]]}
                for row in payload["title_genres"]
            ]
            credits = [
                {
                    "title_id": title_ids[row["title_ref"]],
                    "person_id": person_ids[row["person_ref"]],
                    "role": row["role"],
                }
                for row in payload["credits"]
            ]
            if title_genres:
                connection.execute(insert(metadata.tables["title_genres"]), title_genres)
            if credits:
                connection.execute(insert(metadata.tables["credits"]), credits)

        counts = {table: len(payload[table]) for table in TABLE_NAMES}
        logger.info("Load selesai (commit): %s", counts)
        return counts
    except (SQLAlchemyError, OSError, ValueError, KeyError, IndexError):
        logger.exception("Load gagal; perubahan batch tidak di-commit")
        raise
    finally:
        if engine is not None:
            engine.dispose()


def main():
    records = extract()
    if records is None:
        return None
    payload = transform(records)
    return load(payload)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
