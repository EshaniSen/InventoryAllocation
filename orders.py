import pandas as pd
import streamlit as st
from io import BytesIO


def calculate_allocation(df_sorted, orders_df):
    # Make a copy of the original DataFrame to preserve the original "Total Stock" and "In Hand Qty" values
    df_original = df_sorted.copy()

    # Convert the "Freshness" column to numeric format (e.g., 0.30) for calculations
    df_sorted['Freshness'] = df_sorted['Freshness'].str.rstrip('%').astype(float) / 100

    # Convert the "MFG Date" column to datetime.date
    df_sorted['MFG Date'] = pd.to_datetime(df_sorted['MFG Date']).dt.date

    # Sort the DataFrame by warehouse, promotion, and manufacturing date in ascending order
    df_sorted = df_sorted.sort_values(['WH', 'Remarks', 'MFG Date'])

    # Create a new DataFrame to store the allocation results
    allocation_df = pd.DataFrame(columns=['lotNo', 'Requested', 'Previous In hand', 'Allocated', 'Remaining In hand'])

    for _, order_row in orders_df.iterrows():
        sku_description = order_row['SKU Description']
        ordered_qty = order_row['Requested QTY']
        warehouse = order_row['WH']
        ordered_date = order_row['Ordered Date']

        # Filter df_sorted for the specific SKU_description and WH
        relevant_rows = df_sorted[(df_sorted['SKU Description'] == sku_description) & (df_sorted['WH'] == warehouse)]

        # Allocate quantities based on promotions first
        promotion_lots = relevant_rows[
            (relevant_rows['Remarks'] == 'Promotion')
            & (relevant_rows['MFG Date'] <= ordered_date)
        ]

        if not promotion_lots.empty and ordered_date.day <= 15:
            for _, row in promotion_lots.iterrows():
                lot_no = row['lotNo']
                in_hand_qty = row['IN_HAND_QTY']

                # Calculate the allocation quantity for this lotNo (considering FIFO)
                allocation_qty = min(ordered_qty, in_hand_qty)
                ordered_qty -= allocation_qty

                # Append the allocation details to the temporary DataFrame
                # Check if the lotNo already exists in allocation_df before appending
                if lot_no not in allocation_df['lotNo'].values:
                    allocation_df = allocation_df.append(
                        {
                            'lotNo': lot_no,
                            'Requested': ordered_qty + allocation_qty,
                            'Previous In hand': in_hand_qty,
                            'Allocated': allocation_qty,
                            'Remaining In hand': in_hand_qty - allocation_qty,
                        },
                        ignore_index=True,
                    )

                # Update the in-hand stock and total stock in df_sorted
                df_sorted.at[_, 'IN_HAND_QTY'] -= allocation_qty
                df_sorted.at[_, 'Total Stock'] -= allocation_qty

                if ordered_qty <= 0:
                    break

        # Allocate the remaining quantities based on freshness (FIFO) for ordered date after 15th
        if ordered_qty > 0:
            for _, row in relevant_rows[
                (relevant_rows['Remarks'] != 'Promotion')].iterrows():
                lot_no = row['lotNo']
                in_hand_qty = row['IN_HAND_QTY']

                # Calculate the allocation quantity for this lotNo (considering FIFO)
                allocation_qty = min(ordered_qty, in_hand_qty)
                ordered_qty -= allocation_qty

                # Append the allocation details to the temporary DataFrame
                # Check if the lotNo already exists in allocation_df before appending
                if lot_no not in allocation_df['lotNo'].values:
                    allocation_df = allocation_df.append(
                        {
                            'lotNo': lot_no,
                            'Requested': ordered_qty + allocation_qty,
                            'Previous In hand': in_hand_qty,
                            'Allocated': allocation_qty,
                            'Remaining In hand': in_hand_qty - allocation_qty,
                        },
                        ignore_index=True,
                    )

                # Update the in-hand stock and total stock in df_sorted
                df_sorted.at[_, 'IN_HAND_QTY'] -= allocation_qty
                df_sorted.at[_, 'Total Stock'] -= allocation_qty

                if ordered_qty <= 0:
                    break

    # Set the "Requested" and "Allocated" quantity to 0 for rows in df_sorted where no requested quantity is assigned
    df_sorted['Requested Qty'] = 0
    df_sorted['Allocated Qty'] = 0

    # Set "Previous In hand" and "Remaining In hand" to "IN_HAND_QTY" when no requested quantity is assigned
    df_sorted['Previous In hand'] = df_sorted['IN_HAND_QTY']
    df_sorted['Remaining In hand'] = df_sorted['IN_HAND_QTY']

    # Convert the "Freshness" column to percentages in df_sorted
    df_sorted['Freshness'] = (df_sorted['Freshness'] * 100).round(2).astype(str) + '%'

    # Format the "MFG Date" and "Expiration Date" columns to "dd-mm-yyyy" format in df_sorted
    df_sorted['MFG Date'] = pd.to_datetime(df_sorted['MFG Date']).dt.strftime('%d-%m-%Y')
    df_sorted['Expiration Date'] = pd.to_datetime(df_sorted['Expiration Date']).dt.strftime('%d-%m-%Y')

    # Restore the original "Total Stock" and "In Hand Qty" values from df_original
    df_sorted['Total Stock'] = df_original['Total Stock']
    df_sorted['IN_HAND_QTY'] = df_original['IN_HAND_QTY']

    return df_sorted, allocation_df







# Streamlit app

st.markdown("<h1 style='text-align: center;'>Inventory Management</h1>", unsafe_allow_html=True)

uploaded_inventory_file = st.file_uploader("Upload Inventory File")

if uploaded_inventory_file is not None:
    # Read the uploaded inventory file into a DataFrame
    inventory_df = pd.read_excel(uploaded_inventory_file)

    # Convert 'Freshness' column to string in the inventory DataFrame
    inventory_df['Freshness'] = inventory_df['Freshness'].astype(str)

    # Display the inventory DataFrame
    st.subheader("Input Inventory DataFrame")
    st.write(inventory_df)

    # Upload file for orders
    uploaded_orders_file = st.file_uploader("Upload Orders File")

    if uploaded_orders_file is not None:
        # Read the uploaded orders file into a DataFrame
        orders_df = pd.read_excel(uploaded_orders_file)

        # Display the orders DataFrame
        st.subheader("Orders DataFrame")
        st.write(orders_df)

        # Calculate allocation
        df_sorted, allocation_df = calculate_allocation(inventory_df, orders_df)

        # Merge original DataFrame with allocation DataFrame based on lotNo
        merged_df = pd.merge(df_sorted, allocation_df, on='lotNo', how='left')

        # Merge the "Ordered Date" from orders_df into the merged DataFrame based on SKU and warehouse
        merged_df = pd.merge(merged_df, orders_df[['SKU Description', 'WH', 'Ordered Date']], on=['SKU Description', 'WH'], how='left')

        # Set the "Requested" and "Allocated" quantity to 0 for rows where no corresponding order date is available
        merged_df['Requested'] = merged_df.apply(
        lambda row: row['Requested'] if pd.notnull(row['Ordered Date']) else 0,
        axis=1)
        
        merged_df['Allocated'] = merged_df.apply(
        lambda row: row['Allocated'] if pd.notnull(row['Ordered Date']) else 0,
        axis=1)



        # Set the "Requested" and "Allocated" quantity to 0 for rows in merged_df where no requested quantity is assigned
        #merged_df['Requested'] = merged_df['Requested'].fillna(0)
        #merged_df['Allocated'] = merged_df['Allocated'].fillna(0)

        # Combine logic for "Previous In hand" columns into a single "Previous In hand" column
        merged_df['Previous In hand'] = merged_df.apply(
         lambda row: row['IN_HAND_QTY'] if row['Requested'] == 0 else row['Previous In hand_x'],
          axis=1)
          
        # Drop the unnecessary "Previous In hand" columns
        merged_df = merged_df.drop(columns=['Previous In hand_x', 'Previous In hand_y'])

        # Combine logic for "Remaining In hand" columns into a single "Remaining In hand" column
        merged_df['Remaining In hand'] = merged_df.apply(
             lambda row: row['IN_HAND_QTY'] if row['Requested'] == 0 else row['Remaining In hand_x'],
             axis=1
        )
        # Drop the unnecessary "Remaining In hand" columns
        merged_df = merged_df.drop(columns=['Remaining In hand_x', 'Remaining In hand_y'])

        # Convert the "Freshness" column to numeric format for calculations
        merged_df['Freshness'] = merged_df['Freshness'].str.rstrip('%').astype(float) / 100

        # Format the "Freshness" column to percentages in merged_df
        merged_df['Freshness'] = (merged_df['Freshness'] * 100).round(2).astype(str) + '%'

        # Format the "MFG Date" and "Expiration Date" columns to "dd-mm-yyyy" format in merged_df
        #merged_df['MFG Date'] = pd.to_datetime(merged_df['MFG Date']).dt.strftime('%d-%m-%Y')
        #merged_df['Expiration Date'] = pd.to_datetime(merged_df['Expiration Date']).dt.strftime('%d-%m-%Y')
        merged_df['Ordered Date'] = pd.to_datetime(merged_df['Ordered Date']).dt.strftime('%d-%m-%Y')

        # Drop unwanted columns from the merged DataFrame
        columns_to_drop = ['IN_TRANSIT_QTY', 'Requested Qty', 'Allocated Qty','Previous In hand']  
        merged_df = merged_df.drop(columns=columns_to_drop)

        # Display the updated DataFrame with original quantities for the selected SKU and warehouse
        st.subheader("Updated DataFrame")
        st.write(merged_df)

        
        # Dropdowns to select SKU Description and Warehouse for filtering
        selected_sku = st.selectbox("Select SKU Description", merged_df['SKU Description'].unique())
        selected_warehouse = st.selectbox("Select Warehouse", merged_df['WH'].unique())

        # Filter the data based on the selected SKU Description and Warehouse
        filtered_df = merged_df[
            (merged_df['SKU Description'] == selected_sku) & (merged_df['WH'] == selected_warehouse)
        ]

        # Display the filtered DataFrame
        st.subheader("Filtered DataFrame")
        st.write(filtered_df)



 # Provide a link to download the merged DataFrame as an Excel file
    
        excel_data = BytesIO()
        output_file = 'Updated_DataFrame.xlsx'
        with pd.ExcelWriter(excel_data, engine='openpyxl') as writer:
            merged_df.to_excel(writer, index=False, sheet_name='Updated_DataFrame')
        st.download_button(
            label="Download File as Excel",
            data=excel_data.getvalue(),
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


