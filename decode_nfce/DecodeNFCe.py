import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os

path_ncm_table = "./data/NCM_Tabela.csv"

class DecodeNFCe:
    def __init__(self):
        self.regex_NCM = "NCM</label><span>(\\d{1,20})</span>"
        self.regex_vlr_unit = "comercialização</label><span>(\\d{1,5},\\d{1,2})"
        self.regex_estab = 'Social</label><span>([^>]*)</span>'
        self.regex_CNPJ = 'CNPJ</label><span>([^>]*)</span>'
        self.regex_dt_emissao = 'Emissão</label><span>(\\d{2}/\\d{2}/\\d{2,4})'
        self.regex_valor_total = 'Fiscal\\s\\s</label><span>(\\d{1,5},\\d{1,2})</span>'
        if os.path.exists(path_ncm_table):
            self.base_NCM = pd.read_csv(path_ncm_table)
    
    def get_data(self, page, chave, columns):
        print("[INFO] Decoding Data . . .")
        produtos = []

        soup = BeautifulSoup(page.content, 'html.parser')

        div_emitente = soup.find('div', id='Emitente')
        nfce_no_estabelecimento = re.findall(self.regex_estab, div_emitente.decode_contents())[0]
        nfce_nu_cnpj_estabelecimento = re.findall(self.regex_CNPJ, div_emitente.decode_contents())[0]

        div_nfe = soup.find('div', id='NFe').find('fieldset')
        nfce_dt_emissao = re.findall(self.regex_dt_emissao, div_nfe.decode_contents())[0]
        nfce_valor_total = re.findall(self.regex_valor_total, div_nfe.decode_contents())[0]

        div_prod = soup.find('div', id='Prod')
        table_toggle_prod = div_prod.find_all('table', class_='toggle box')

        for prod_serv in table_toggle_prod:
            #numero = prod_serv.find(class_="fixo-prod-serv-numero").get_text()
            descricao = prod_serv.find(class_="fixo-prod-serv-descricao").get_text()
            qt_produto = prod_serv.find(class_="fixo-prod-serv-qtd").get_text()
            no_unidade_medida = prod_serv.find(class_="fixo-prod-serv-uc").get_text()
            vr_total_produto = prod_serv.find(class_="fixo-prod-serv-vb").get_text()

            produtos.append([nfce_dt_emissao,
                            nfce_valor_total,
                            nfce_nu_cnpj_estabelecimento,
                            nfce_no_estabelecimento,
                            descricao, 
                            qt_produto, 
                            no_unidade_medida, 
                            vr_total_produto])


        nfce_vr_unitario = re.findall(self.regex_vlr_unit, div_prod.decode_contents())
        nfce_codigos_NCM = re.findall(self.regex_NCM, div_prod.decode_contents())

        retorno = pd.DataFrame(produtos, columns=['dt_emissao',
                                                'vr_total_NF',
                                                'nu_cnpj_estabelecimento',
                                                'no_estabelecimento',
                                                'de_produto', 
                                                'qt_produto', 
                                                'no_unidade_medida', 
                                                'vr_total_produto']
                                                )

        retorno['vr_unitario'] = nfce_vr_unitario
        retorno['co_NCM_produto'] = nfce_codigos_NCM
        retorno['nu_chave'] = chave
        retorno = pd.merge(retorno, self.base_NCM, on='co_NCM_produto')

        retorno = retorno[columns]

        return retorno