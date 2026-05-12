https://learn.microsoft.com/en-us/microsoft-copilot-studio/guidance/architecture/multi-agent-orchestrator-sub-agent

Orchestrator and subagent multi-agent patterns - Microsoft Copilot Studio | Microsoft Learn 
			 
			 
			 

			 
			  

			 
			 
			 
			 
			 
			 
			 
			 
			 
			 
			   
			 
			 
			 

			 

			 
			

			 
			
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	 
		 
	
		 
	
		 
	
		 
	
		 
	
		 
	

			 
			
			 
			
			  
			  
			  

			 
			 
		var msDocs = {
  "environment": {
    "accessLevel": "online",
    "azurePortalHostname": "portal.azure.com",
    "reviewFeatures": false,
    "supportLevel": "production",
    "systemContent": true,
    "siteName": "learn",
    "legacyHosting": false
  },
  "data": {
    "contentLocale": "en-us",
    "contentDir": "ltr",
    "userLocale": "en-us",
    "userDir": "ltr",
    "pageTemplate": "Conceptual",
    "brand": "",
    "context": {},
    "standardFeedback": true,
    "showFeedbackReport": false,
    "feedbackHelpLinkType": "",
    "feedbackHelpLinkUrl": "",
    "feedbackSystem": "Standard",
    "feedbackGitHubRepo": "",
    "feedbackProductUrl": "https://powerusers.microsoft.com/t5/Power-Virtual-Agents-Community/ct-p/PVACommunity",
    "extendBreadcrumb": false,
    "isEditDisplayable": false,
    "isPrivateUnauthorized": false,
    "hideViewSource": false,
    "isPermissioned": false,
    "hasRecommendations": true,
    "contributors": [
      {
        "name": "TheBluLion",
        "url": "https://github.com/TheBluLion"
      },
      {
        "name": "jhaskett-msft",
        "url": "https://github.com/jhaskett-msft"
      },
      {
        "name": "manuelap-msft",
        "url": "https://github.com/manuelap-msft"
      }
    ]
  },
  "functions": {}
};;
	 

			 
			  
			

			 
			
		 
	
			 
				 
		 
			
		 
			Skip to main content
		 
	
		 
			Skip to Ask Learn chat experience
		 
	

			  
			 
			 
				 
					 This browser is no longer supported. 
					 
						Upgrade to Microsoft Edge to take advantage of the latest features, security updates, and technical support.
					 
					 
						 
							Download Microsoft Edge
						 
						 
							More info about Internet Explorer and Microsoft Edge
						 
					 
				 
			 
			 
			 
				  
				  
				  
			 
			
		 
		 
			  
			
		 
		 
	
		 
	 
				  
					
		 
			 
				 
					 
						 
							 
								  
							 
						 
						  
					 
				 
			 
		 
	
			   

				 
					
			 
		 
			 
				    
				  Table of contents  
			 
			 
				    
				 Exit editor mode 
			 
		 
	 
			 
				 
					
		 
			 
				
		 
			 
				 
					  
				 
			 
			  
		 

		  
	 
		 
			
		 
			 
				  
			 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
	 

			 
				 
					 
						  
					 
				 
				 
					
		 
			 
				  
			 
			 Reading mode 
		 
	 
		 
			    
			 Table of contents 
		 
	 
		 
			 
				  
			 
			 Read in English 
		 
	
					
		 
			 
				  
			 
			 Add 
		 
	 
		 
			 
				  
			 
			 Add to plan 
		 
	 
					
		 
			 
				  
			 
			 Edit 
		 
	  
		 
		
				 
					 
						  
						  
						  
					 
					 Copy Markdown 
				 
		   
				 
					 
						  
					 
					 Print 
				 
		  
	
				 
			 
		 
	
			 
		 
	  
		 
		 
			 
			 
				 
					 
						    
						 Note 
					 
					 
						Access to this page requires authorization. You can try  signing in  or  changing directories .
					 
					 
						Access to this page requires authorization. You can try  changing directories .
					 
				 
			 
		 
	
					  Orchestrator and subagent multi-agent patterns  
					
		 
			 
				 
					
		 
			 
				  
			 
			 Feedback 
		 
	
				 
		  
		 
	 
		 
			 
				 
					  
				 
				 
					 
						Summarize this article for me
					 
				 
			 
			 
			  
		 
	 
		 
			 
				In this article
			 
		 
	
					  A primary orchestrator delegates tasks to a set of subordinate specialist agents. These specialist subagents can be "child agents" managed within the same solution, or external "connected agents" (standalone agents that different teams or business units own and maintain). 
 This hierarchical pattern is ideal for clear separation of concerns. For example, a Sales Copilot agent might orchestrate one agent for lead scoring and another for generating proposals. The orchestrator manages the overall user conversation and high-level decisions ("do we need to involve another agent?"), while subagents focus on execution. 
 Use this pattern (also referred to as "Russian doll" or  magentic  patterns) when the top-down solution can be naturally broken into domains or functional areas. It's especially useful when modularity, independent ownership, or reuse is important. This approach creates a simpler user experience with one entry point, while using multiple agents optimized for quality and reliability for their targeted domain or function. 
 Use this pattern when: 
 
 The use case is open-ended with no predetermined process flow. 
 Specialist agents are already available and optimized for reuse or explicitly needed to provide tuned or specialized quality for the use case. 
 The use case tolerates or benefits from "spray and pray" approaches, where a single success justifies all prior failed attempts. 
 
 Example use cases include vibe coding, red teaming, and modeling potential new vaccines or chemical compounds. This pattern also works well when the user is educated to generate several responses and selects the best result for further evaluation or refinement. 
 Don't use this pattern when: 
 
 The use case requires a consistent success rate (compliance or Q&A use cases). 
 The process includes well-defined steps and strong hierarchical dependencies. 
 The process is time-sensitive and can't tolerate waiting for failed plans or responses to retry. 
 The component agents require long response windows or require large request and response sizes that exceed the limitations of the primary orchestrator. 
 
 Learn more about  magentic orchestration . 
 
					
		  
	 
		  
		  
	
					
		 
		 
			 
			 Feedback 
			 
				 
					Was this page helpful?
				 
				 
					 
						 
							  
						 
						 Yes 
					 
					 
						 
							  
						 
						 No 
					 
					 
						 
							 
								  
							 
							 No 
						 
						 
							 
								Need help with this topic?
							 
							 
								Want to try using Ask Learn to clarify or guide you through this topic?
							 
							
		 
			 
		 
			 
				  
			 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
	 
			 
				 
					  
				 
				  Suggest a fix?  
			 
		 
	
						 
					 
				 
			 
		 
		 
	
				 
				
		 
			 
			 
				Additional resources
			 
			
		  
	 
		  
	 
		  
	
		 
	 
		 
			 
			 
				 
			 
				 Last updated on  
		2026-02-04
	  
			 
		 
			 
		 
	
			 
			
		  
	
		
				 
				 
					
		 
			 
				
		 
			 In this article 
		 
	
				 
				
		 
			 Was this page helpful? 
			 
				 
					 
						  
					 
					 Yes 
				 
				 
					 
						  
					 
					 No 
				 
				 
					 
						 
							  
						 
						 No 
					 
					 
						 
							Need help with this topic?
						 
						 
							Want to try using Ask Learn to clarify or guide you through this topic?
						 
						
		 
			 
		 
			 
				  
			 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
		 
			 
				  
			 
			 Ask Learn 
		 
	 
			 
				 
					  
				 
				  Suggest a fix?  
			 
		 
	
					 
				 
			 
		 
	
			 
		 
	
			     
					   
			     
		 
			 
				
		      en-us  
	  
		
		 
		 
			  
			  
			  
			  
		 
	
			 Your Privacy Choices  
	
	 
				 
		 
			 
				    
				 Theme 
				 
					  
				 
			 
			 
				 
					 
						 
							 
								 
									 
										 
										 
										 
										 
										 
										 
										 
										 
									 
								 
							 
							  Light  
						 
					 
					 
						 
							 
								 
									 
										 
										 
										 
										 
										 
										 
										 
										 
									 
								 
							 
							  Dark  
						 
					 
					 
						 
							 
								 
									 
										 
										 
										 
										 
										 
										 
										 
										 
									 
								 
							 
							  High contrast  
						 
					 
				 
			 
		 
	 
			 
			 
				  
				 
		
		 AI Disclaimer 
	
	  
		
		 Previous Versions 
	
	   
		
		 Blog 
	
	   
		
		 Contribute 
	
	  
		
		 Privacy 
	
	  
		
		 Consumer Health Privacy 
	
	  
		
		 Terms of Use 
	
	  
		
		 Trademarks 
	
	 
				 © Microsoft 2026
