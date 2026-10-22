from hashlib import sha256
from io import BytesIO
import re

import pandas as pd
import streamlit as st


MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_COLUMNS = 100
MAX_ROWS = 100_000


def read_csv(contents: bytes) -> pd.DataFrame:
    """Validate and parse uploaded CSV bytes."""
    if not contents:
        raise ValueError("The file is empty.")

    if len(contents) > MAX_FILE_SIZE:
        raise ValueError("Maximum file size is 5 MB.")

    try:
        df = pd.read_csv(BytesIO(contents))
    except (
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        raise ValueError("Could not read this CSV file.") from exc

    if df.empty:
        raise ValueError("The CSV has no data rows.")

    if len(df.columns) > MAX_COLUMNS or len(df) > MAX_ROWS:
        raise ValueError("Dataset exceeds the allowed limits.")

    if not df.columns.is_unique:
        raise ValueError("Column names must be unique.")

    return df


@st.cache_data
def load_csv(contents: bytes) -> pd.DataFrame:
    """Cache the parsed DataFrame for this uploaded file."""
    return read_csv(contents)


def get_numeric_columns(df: pd.DataFrame) -> list:
    return df.select_dtypes(include="number").columns.tolist()


def find_column(question: str, columns: list) -> str | None:
    """Find a dataset column mentioned in a question."""
    question_lower = question.lower()

    # Prefer the longest matching column name.
    for column in sorted(columns, key=lambda item: len(str(item)), reverse=True):
        name = str(column).strip().lower()
        if name and re.search(
            rf"(?<!\w){re.escape(name)}(?!\w)",
            question_lower,
        ):
            return column

    return None


def analyze_question(df: pd.DataFrame, question: str) -> dict:
    question_lower = question.strip().lower()
    numeric_columns = get_numeric_columns(df)
    columns = df.columns.tolist()

    if not question_lower:
        return {"answer": "Please enter a question."}

    if any(
        phrase in question_lower
        for phrase in ["summarize", "summary", "overview", "describe dataset"]
    ):
        answer = (
            f"The dataset contains {len(df)} rows and "
            f"{len(columns)} columns. "
            f"Numeric columns: "
            f"{', '.join(map(str, numeric_columns)) or 'None'}. "
            f"Other columns: "
            f"{', '.join(str(column) for column in columns if column not in numeric_columns) or 'None'}."
        )
        return {"answer": answer}

    # Grouped comparisons, such as total sales by category.
    group_match = re.search(
        r"\b(?:by|across|among each|for each|per)\s+(.+?)(?:\?|$)",
        question_lower,
    )
    group_column = find_column(
        group_match.group(1).strip(" ?.")
        if group_match
        else "",
        columns,
    )
    value_column = find_column(question_lower, numeric_columns)

    if (
        group_column is not None
        and value_column is not None
        and group_column != value_column
        and any(
            word in question_lower
            for word in [
                "compare",
                "total",
                "sum",
                "sales",
                "revenue",
                "highest",
                "lowest",
                "average",
                "mean",
                "group",
            ]
        )
    ):
        grouped = df.groupby(group_column, dropna=False)[value_column]

        if any(word in question_lower for word in ["average", "mean"]):
            result = grouped.mean()
            operation = "Average"
        else:
            result = grouped.sum()
            operation = "Total"

        result = result.sort_values(ascending=False)
        items = [
            {"category": str(key), "value": round(float(value), 2)}
            for key, value in result.items()
        ]

        if not items:
            return {"answer": "No groups were available to compare."}

        return {
            "answer": (
                f"{operation} {value_column} grouped by {group_column}. "
                f"Highest: {items[0]['category']} "
                f"({items[0]['value']:,.2f})."
            ),
            "table": items,
            "chart": {
                "labels": [item["category"] for item in items],
                "values": [item["value"] for item in items],
                "label": f"{operation} {value_column}",
            },
        }

    # Find a numeric field for a single-column calculation.
    column = value_column or (
        numeric_columns[0] if len(numeric_columns) == 1 else None
    )

    if column is not None:
        values = df[column].dropna()

        if values.empty:
            return {"answer": f"Column '{column}' has no numeric values."}

        if any(
            word in question_lower
            for word in ["highest", "maximum", "max", "largest", "most"]
        ):
            index = values.idxmax()
            row = df.loc[index]
            details = ", ".join(
                f"{field}: {row[field]}" for field in columns
            )
            return {
                "answer": (
                    f"The highest {column} is {values.max():,.2f}. "
                    f"Record: {details}"
                )
            }

        if any(
            word in question_lower
            for word in ["lowest", "minimum", "min", "smallest", "least"]
        ):
            index = values.idxmin()
            row = df.loc[index]
            details = ", ".join(
                f"{field}: {row[field]}" for field in columns
            )
            return {
                "answer": (
                    f"The lowest {column} is {values.min():,.2f}. "
                    f"Record: {details}"
                )
            }

        if any(word in question_lower for word in ["average", "mean"]):
            return {
                "answer": f"The average {column} is {values.mean():,.2f}."
            }

        if any(
            word in question_lower
            for word in ["total", "sum", "overall", "how much"]
        ):
            return {
                "answer": f"The total {column} is {values.sum():,.2f}."
            }

    if any(
        word in question_lower
        for word in ["count", "how many", "number of rows"]
    ):
        return {
            "answer": (
                f"The dataset contains {len(df)} rows "
                f"and {len(columns)} columns."
            )
        }

    return {
        "answer": (
            "I couldn't identify that analysis yet. Try asking for a "
            "dataset summary, total, average, highest or lowest value, "
            "or a comparison such as 'total sales by category'. "
            f"Available columns: {', '.join(map(str, columns))}."
        )
    }


def render_message(message: dict) -> None:
    """Display one saved chat message, including any table or chart."""
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.write(message["text"])
            return

        result = message["result"]
        st.write(result["answer"])

        if "table" in result:
            st.dataframe(
                pd.DataFrame(result["table"]),
                hide_index=True,
                use_container_width=True,
            )

        if "chart" in result:
            chart = result["chart"]
            chart_df = pd.DataFrame({
                chart["label"]: chart["values"],
            }, index=chart["labels"])
            st.bar_chart(chart_df)


def main() -> None:
    st.set_page_config(
        page_title="DataQuery AI",
        page_icon="📊",
        layout="wide",
    )

    st.title("DataQuery AI")
    st.write("Upload a CSV file and ask questions about its data.")

    uploaded_file = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        help="Maximum file size: 5 MB.",
    )

    if uploaded_file is None:
        st.info("Choose a CSV file to get started.")
        return

    if not uploaded_file.name.lower().endswith(".csv"):
        st.error("Please upload a CSV file.")
        return

    contents = uploaded_file.getvalue()
    file_hash = sha256(contents).hexdigest()

    if st.session_state.get("upload_hash") != file_hash:
        st.session_state["upload_hash"] = file_hash
        st.session_state["messages"] = []

    try:
        df = load_csv(contents)
    except ValueError as exc:
        st.error(str(exc))
        return

    st.success(f"CSV file uploaded successfully: {uploaded_file.name}")

    numeric_columns = get_numeric_columns(df)
    other_columns = [
        column for column in df.columns
        if column not in numeric_columns
    ]

    metric_columns = st.columns(3)
    metric_columns[0].metric("Rows", f"{len(df):,}")
    metric_columns[1].metric("Columns", len(df.columns))
    metric_columns[2].metric("Numeric columns", len(numeric_columns))

    st.subheader("Data preview")
    st.caption(f"Showing the first {min(10, len(df))} rows.")
    st.dataframe(df.head(10), hide_index=True, use_container_width=True)

    with st.expander("Column information"):
        st.write("**Numeric columns:**", ", ".join(map(str, numeric_columns)) or "None")
        st.write("**Other columns:**", ", ".join(map(str, other_columns)) or "None")
        st.dataframe(
            pd.DataFrame({
                "Column": df.columns,
                "Data type": [str(dtype) for dtype in df.dtypes],
            }),
            hide_index=True,
            use_container_width=True,
        )

    st.subheader("Ask about your data")

    with st.form("question_form", clear_on_submit=True):
        question = st.text_input(
            "Your question",
            max_chars=500,
            placeholder="For example: What is the total sales?",
        )
        submitted = st.form_submit_button("Ask")

    if submitted:
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            st.session_state["messages"].append({
                "role": "user",
                "text": question.strip(),
            })
            st.session_state["messages"].append({
                "role": "assistant",
                "result": analyze_question(df, question),
            })

    for message in st.session_state.get("messages", []):
        render_message(message)


if __name__ == "__main__":
    main()