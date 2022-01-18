
import gspread
from oauth2client.service_account import ServiceAccountCredentials


class GoogleSpreadSheet:

    def __init__(self, scope_sheets, path_credentials, spreadsheet_key):
        self.spreadsheet_key = spreadsheet_key
        #Create a credential to access the Spread Sheet on Google Drive
        self.credentials = ServiceAccountCredentials.from_json_keyfile_name(path_credentials, scope_sheets)

        self.gc = gspread.authorize(self.credentials)

    def get_work_sheet(self, sheet_id=0):
        #Open the Google Sheet by the Sheet ID
        dados_coupons = self.gc.open_by_key(self.spreadsheet_key)

        #Open first Sheet in the file
        coupons_sheet = dados_coupons.get_worksheet(sheet_id)

        return coupons_sheet

    def save_data_gspread(self, df_dados):
        try:
            #Open the Worksheet in the Google Drive
            worksheet = self.get_work_sheet()
            #Convert DataFrame to list
            df_values = df_dados.values.tolist() 
            #Append values in the Spreadsheet
            worksheet.append_rows(values=df_values)
            
            return True
        except Exception as e:
            print('[ERROR]', e)
            
            return False
