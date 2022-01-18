import pandas as pd
import pymssql
from sqlalchemy import create_engine

path_csv_coupons = "../data/coupons.csv"

#============================================
server = "rrpronaldo-sqlserver.database.windows.net:1433"
user = ""
password = ""
database = "rrpronaldo-sqlserver"
driver = "ODBC Driver 17 for SQL Server"

# Create engine to interact with database
engine_azure = create_engine(f'mssql+pymssql://{user}:{password}@{server}/{database}')

#============================================
df_coupons = pd.read_csv(path_csv_coupons)

#Convert columns from object to float
columns_float = ["qt_produto","vr_unitario", "vr_total_produto", "vr_total_NF", "co_NCM_produto"]
for column in columns_float:
    df_coupons[column] = df_coupons[column].replace(",",".", regex=True).astype('float64')

    
#Convert date columns to datetime
df_coupons["dt_emissao"] = pd.to_datetime(df_coupons["dt_emissao"], format="%d/%m/%Y")

df_coupons.head()

#============================================
#Insert data into database
tb_name = 'TB_COUPONS'
df_coupons.to_sql(tb_name, engine_azure, if_exists='append', index=False)

#============================================
engine_azure.dispose()