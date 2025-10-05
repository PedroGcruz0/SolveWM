import psycopg2


conn = psycopg2.connect(
    host="localhost",
    database="Teste",
    user="postgres",
    password="Kayki1335",
    port=5432
)

cursor = conn.cursor()
cursor.execute('SELECT * FROM "cadastro";')
linhas= cursor.fetchall()
#print(linhas)



emails= []
senhas= []


for linha in linhas:
    emails.append(linha[1])
    senhas.append(linha[2])
   

print(emails)
print(senhas)




cursor.close()
conn.close()




from flask import Flask, render_template, request

app = Flask(__name__)

# Rota principal, que renderiza a página HTML
@app.route('/')
def index():
    return render_template('index.html')  # seu arquivo HTML

# Rota que recebe dados do HTML (exemplo de formulário)
@app.route('/enviar', methods=['POST'])
def enviar():
    # Pegar os valores do formulário
    password = request.form['password']    # armazena o valor do input "password"
    email = request.form['email']  # armazena o valor do input "email"

    
    #print(email, password)
    if email in emails:
        index = emails.index(email)  # pega a posição do email
        if senhas[index] == password:   # verifica se a senha tem o mesmo índice
            return "Login correto!"
        else:
            return "Senha incorreta!"
    else:
        return "Email incorreto!" 


if __name__ == '__main__':
    app.run(debug=True)





