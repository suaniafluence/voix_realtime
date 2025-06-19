describe('Home page', () => {
  it('loads', () => {
    cy.visit('/')
    cy.contains('Connexion', { matchCase: false })
  })
})
